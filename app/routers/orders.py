from fastapi import APIRouter, Depends, Query, Body
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.order import Order
from app.core.permissions import require_role
from app.deps import get_current_user
from app.utils.order_code import generate_order_code
from fastapi import UploadFile, File
from app.services.google_drive import upload_file_to_drive
from app.models.order_file import OrderFile
from app.core.file_rules import FILE_RULES
from fastapi import HTTPException
import traceback
from sqlalchemy.exc import IntegrityError
from app.utils.order_log import log_order_change
from app.models.order_log import OrderLog
from app.core.order_rules import (
    can_edit_shipping_address,
    can_edit_product,
    can_edit_freebie_note,
    can_edit_payment
)
from app.models.order_payment import OrderPayment
from app.core.status_sync import sync_order_status_with_payment
from app.core.order_status_rules import can_change_order_status
from app.utils.order_alert import create_order_alert
from app.models.order_alert import OrderAlert
from datetime import date, datetime, timedelta
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.order_item_freebie import OrderItemFreebie
from app.models.freebie import Freebie
from app.schemas.order_create import OrderCreate
from sqlalchemy import func
from datetime import date
from fastapi.responses import StreamingResponse
import io
from openpyxl import Workbook
from app.models.order_freebie import OrderFreebie
from app.models.user import User
from app.models.page_name import PageName
from app.services.line_messaging import send_order_created_notification

router = APIRouter(prefix="/orders")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _order_net_total(db: Session, order_id: int) -> float:
    """Sum of (unit_price - discount) for all order items."""
    items = db.query(OrderItem).filter(OrderItem.order_id == order_id).all()
    return sum(float(i.unit_price) - float(i.discount) for i in items)


from fastapi import Form

@router.post("")
def create_order(
    data: OrderCreate,
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    require_role(user, ["sale", "manager"])

    shipping_address_safe = ((data.shipping_address or "").strip() or "")[:255]
    max_attempts = 3

    for attempt in range(max_attempts):
        try:
            # 1️⃣ สร้าง Order
            order_code = generate_order_code(db)
            shipping_method_val = (getattr(data, "shipping_method", None) or "").strip() or "Normal"
            if shipping_method_val.lower() not in ("normal", "special"):
                shipping_method_val = "Normal"
            order = Order(
                order_code=order_code,
                sale_id=user["user_id"],
                customer_name=data.customer_name,
                customer_phone=data.customer_phone,
                shipping_address_text=shipping_address_safe,
                shipping_date=data.shipping_date,
                invoice_required=bool(data.invoice_text),
                invoice_text=data.invoice_text,
                note=data.note,
                shipping_note=data.shipping_note,
                pageName=data.pageName,
                installment_type=data.installment_type,
                installment_months=data.installment_months,
                shipping_method=shipping_method_val,
            )

            db.add(order)
            db.flush()

            # 2️⃣ สร้าง Payment
            payment = OrderPayment(
                order_id=order.id,
                payment_status="Unchecked",
                payment_method=data.payment_method,
                installment_type=data.installment_type,
                installment_months=data.installment_months
            )

            db.add(payment)
            db.commit()

            return {
                "message": "Order created",
                "order_id": order.id
            }

        except Exception as e:
            db.rollback()
            db.expire_all()
            err_msg = str(e).lower()
            is_dup_code = (
                isinstance(e, IntegrityError)
                or "1062" in err_msg
                or "duplicate entry" in err_msg
                or "order_code" in err_msg
            )
            if is_dup_code and attempt < max_attempts - 1:
                continue
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=str(e))

    raise HTTPException(status_code=500, detail="Could not generate unique order code. Please try again.")


@router.post("/{order_id}/notify-created")
def notify_order_created(
    order_id: int,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Trigger LINE notification for a newly created order.
    Call this only after products, freebies, payment and files are saved.
    """
    require_role(user, ["sale", "manager"])
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    # Fire-and-forget LINE notification; ignore errors.
    try:
        send_order_created_notification(db, order.id)
    except Exception:
        pass
    return {"message": "notified"}


@router.post("/{order_id}/upload-file")
def upload_order_file(
    order_id: int,
    file_type: str = Form(...),
    file: UploadFile = File(...),
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # 1. เช็คว่า file_type ถูกต้องไหม
    if file_type not in FILE_RULES:
        raise HTTPException(
            status_code=400,
            detail="Invalid file type"
        )

    rule = FILE_RULES[file_type]

    # 2. เช็ค Role
    if user["role"] not in rule["roles"]:
        raise HTTPException(
            status_code=403,
            detail="Permission denied for this file type"
        )

    # 3. For payment_slip replace: only when payment status is Unchecked; delete existing slip(s) first
    if file_type == "payment_slip":
        payment = db.query(OrderPayment).filter(OrderPayment.order_id == order_id).first()
        if payment and (payment.payment_status or "").strip() != "Unchecked":
            raise HTTPException(
                status_code=400,
                detail="Cannot upload or replace payment slip when payment status is not Unchecked.",
            )
        db.query(OrderFile).filter(
            OrderFile.order_id == order_id,
            OrderFile.file_type == "payment_slip",
        ).delete(synchronize_session=False)

    # 4. อ่านไฟล์
    file_bytes = file.file.read()

    # 5. Upload Google Drive (may fail if network/DNS cannot reach Google)
    try:
        file_url = upload_file_to_drive(
            file=file_bytes,
            filename=file.filename,
            folder_id=rule["folder_id"]
        )
    except Exception as e:
        err_msg = str(e).lower()
        if "oauth2.googleapis.com" in err_msg or "unable to find the server" in err_msg or "getaddrinfo failed" in err_msg or "transport" in err_msg:
            raise HTTPException(
                status_code=503,
                detail="Cannot reach Google Drive. Check your internet connection and try again."
            ) from e
        raise

    # 6. Save DB
    order_file = OrderFile(
        order_id=order_id,
        file_type=file_type,
        file_url=file_url,
        uploaded_by=user["user_id"]
    )

    db.add(order_file)

    db.commit()

    return {"url": file_url}


@router.delete("/{order_id}/invoice-submit-files/{file_id}")
def delete_invoice_submit_file(
    order_id: int,
    file_id: int,
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    require_role(user, ["manager"])

    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    target_file = (
        db.query(OrderFile)
        .filter(
            OrderFile.id == file_id,
            OrderFile.order_id == order_id,
            OrderFile.file_type == "invoice_submit",
        )
        .first()
    )
    if not target_file:
        raise HTTPException(status_code=404, detail="Invoice submit file not found")

    db.delete(target_file)
    db.commit()
    return {"message": "Invoice submit file deleted", "file_id": file_id}

@router.put("/{order_id}/address")
def update_shipping_address(
    order_id: int,
    new_address: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # 🔒 เช็คกฎตรงนี้
    if not can_edit_shipping_address(user["role"], order.order_status):
        raise HTTPException(
            status_code=403,
            detail="Cannot edit shipping address in current order status"
        )

    old_address = order.shipping_address_text
    order.shipping_address_text = new_address

    log_order_change(
        db=db,
        order_id=order.id,
        action="UPDATE_SHIPPING_ADDRESS",
        old_value=old_address,
        new_value=new_address,
        user_id=user["user_id"]
    )

    create_order_alert(
    db=db,
    order_id=order.id,
    alert_type="UPDATE_SHIPPING_ADDRESS",
    message="มีการแก้ไขที่อยู่จัดส่ง",
    target_role="pack"
    )

    db.commit()

    return {"message": "Shipping address updated"}


@router.put("/{order_id}/customer")
def update_customer(
    order_id: int,
    customer_name: str,
    customer_phone: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if not can_edit_shipping_address(user["role"], order.order_status):
        raise HTTPException(status_code=403, detail="Cannot edit customer in current order status")
    order.customer_name = customer_name
    order.customer_phone = customer_phone
    log_order_change(db=db, order_id=order.id, action="UPDATE_CUSTOMER", old_value="", new_value=f"{customer_name} / {customer_phone}", user_id=user["user_id"])
    db.commit()
    return {"message": "Customer updated"}


@router.put("/{order_id}/shipping-note")
def update_shipping_note(
    order_id: int,
    new_note: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if not can_edit_shipping_address(user["role"], order.order_status):
        raise HTTPException(status_code=403, detail="Cannot edit shipping note in current order status")
    old_note = order.shipping_note or ""
    order.shipping_note = new_note or None
    log_order_change(db=db, order_id=order.id, action="UPDATE_SHIPPING_NOTE", old_value=old_note, new_value=new_note or "", user_id=user["user_id"])
    create_order_alert(db=db, order_id=order.id, alert_type="UPDATE_SHIPPING_NOTE", message="มีการแก้ไขหมายเหตุจัดส่ง", target_role="pack")
    db.commit()
    return {"message": "Shipping note updated"}


@router.put("/{order_id}/note")
def update_order_note(
    order_id: int,
    new_note: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update order freebie note. Editable only when order status is not Shipped or above."""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if not can_edit_freebie_note(user["role"], order.order_status):
        raise HTTPException(status_code=403, detail="Cannot edit freebie note when order is Shipped or above")
    old_note = order.note or ""
    order.note = new_note or None
    log_order_change(db=db, order_id=order.id, action="UPDATE_ORDER_NOTE", old_value=old_note, new_value=new_note or "", user_id=user["user_id"])
    create_order_alert(
        db=db,
        order_id=order.id,
        alert_type="UPDATE_FREEBIE_NOTE",
        message="มีการแก้ไขหมายเหตุของแถม",
        target_role="pack",
    )
    db.commit()
    return {"message": "Freebie note updated"}


@router.put("/{order_id}/invoice")
def update_order_invoice(
    order_id: int,
    invoice_required: bool,
    invoice_text: str | None = None,
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update invoice request. Editable in all status. Creates alert for account when changed."""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    old_required = getattr(order, "invoice_required", False)
    old_text = order.invoice_text or ""

    order.invoice_required = invoice_required
    order.invoice_text = (invoice_text or None) if invoice_required else None

    changed = old_required != invoice_required or old_text != (invoice_text or "")
    if changed:
        create_order_alert(
            db=db,
            order_id=order.id,
            alert_type="UPDATE_INVOICE",
            message="มีการแก้ไขรายละเอียดใบกำกับภาษี",
            target_role="account",
        )

    db.commit()
    return {"message": "Invoice request updated"}


@router.get("/page-names")
def list_page_names(
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all saved page names (for Create Order dropdown)."""
    require_role(user, ["sale", "manager", "account", "pack"])
    rows = db.query(PageName).order_by(PageName.name.asc()).all()
    return [{"id": r.id, "name": r.name} for r in rows]


@router.post("/page-names")
def create_page_name(
    name: str = Body(..., embed=True),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new page name (manager only)."""
    require_role(user, ["manager"])
    cleaned = (name or "").strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="Name is required.")
    exists = db.query(PageName).filter(PageName.name == cleaned).first()
    if exists:
        return {"id": exists.id, "name": exists.name}
    row = PageName(name=cleaned)
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "name": row.name}


@router.delete("/page-names/{page_name_id}")
def delete_page_name(
    page_name_id: int,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a page name (manager only)."""
    require_role(user, ["manager"])
    row = db.query(PageName).filter(PageName.id == page_name_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(row)
    db.commit()
    return {"message": "Deleted"}


@router.get("/invoice-number-pending")
def list_orders_missing_invoice_number(
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Orders that have no invoice_number yet (all orders)."""
    require_role(user, ["account", "manager"])
    orders = (
        db.query(Order, OrderPayment)
        .join(OrderPayment, OrderPayment.order_id == Order.id)
        .filter(
            func.coalesce(func.trim(Order.invoice_number), "") == "",
        )
        .order_by(Order.created_at.asc())
        .all()
    )
    result = []
    for order, payment in orders:
        result.append(
            {
                "id": order.id,
                "order_code": order.order_code,
                "customer_name": order.customer_name,
                "sale_id": order.sale_id,
                "invoice_number": order.invoice_number,
                "payment_status": payment.payment_status,
            }
        )
    return result


@router.put("/{order_id}/invoice-number")
def update_invoice_number(
    order_id: int,
    invoice_number: str = Body(..., embed=True),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Set or update invoice_number for an order (account/manager only)."""
    require_role(user, ["account", "manager"])
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    cleaned = (invoice_number or "").strip()
    order.invoice_number = cleaned or None
    db.add(order)
    db.commit()
    return {"message": "Invoice number updated", "invoice_number": order.invoice_number}


@router.get("/{order_id}/logs")
def get_order_logs(
    order_id: int,
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    logs = (
        db.query(OrderLog)
        .filter(OrderLog.order_id == order_id)
        .order_by(OrderLog.performed_at.asc())
        .all()
    )

    return logs


@router.put("/{order_id}/payment-method")
def update_payment_method(
    order_id: int,
    payment_method: str,
    installment_type: str | None = None,
    installment_months: int | None = None,
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # 1️⃣ ดึง payment
    payment = db.query(OrderPayment).filter(
        OrderPayment.order_id == order_id
    ).first()

    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    # 2️⃣ 🔒 Editable only when payment status is Unchecked
    if not can_edit_payment(user["role"], payment.payment_status):
        raise HTTPException(
            status_code=403,
            detail="Payment method can only be edited when payment status is Unchecked",
        )

    # 3️⃣ Update (only create alert when something actually changed)
    new_installment_type = installment_type if installment_type else None
    new_installment_months = installment_months
    old_method = payment.payment_method
    old_installment_type = payment.installment_type
    old_installment_months = payment.installment_months

    payment.payment_method = payment_method
    payment.installment_type = new_installment_type
    payment.installment_months = new_installment_months

    changed = (
        old_method != payment_method
        or old_installment_type != new_installment_type
        or (old_installment_months != new_installment_months and (old_installment_months or new_installment_months))
    )
    if changed:
        create_order_alert(
            db=db,
            order_id=order_id,
            alert_type="UPDATE_PAYMENT_METHOD",
            message="มีการแก้ไขช่องทางการชำระเงิน",
            target_role="account",
        )

    db.commit()

    return {"message": "Payment method updated"}


@router.put("/{order_id}/payment-status")
def update_payment_status(
    order_id: int,
    new_status: str,
    user=Depends(get_current_user),
    paid_date: datetime | None = None,
    paid_note: str | None = None,
    db: Session = Depends(get_db)
):
    # 1️⃣ เช็ค role
    role = user["role"]
    if role not in ["account", "manager", "pack"]:
        raise HTTPException(
            status_code=403,
            detail="Only account/manager/pack can change payment status"
        )

    has_unread_alert = db.query(OrderAlert).filter(
        OrderAlert.order_id == order_id,
        OrderAlert.target_role == "account",
        OrderAlert.is_read == False
    ).first()

    if has_unread_alert:
        raise HTTPException(
            status_code=400,
            detail="กรุณารับทราบ Alert ก่อนเปลี่ยนสถานะการชำระเงิน"
        )




    # 2️⃣ ดึง payment
    payment = db.query(OrderPayment).filter(
        OrderPayment.order_id == order_id
    ).first()

    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    old_payment_status = payment.payment_status

    # 2b. จำกัดสิทธิ์ของ pack: เปลี่ยนได้เฉพาะ COD: Unchecked → Checked
    if role == "pack":
        if not (
            (payment.payment_method or "").strip().lower() == "cod"
            and (old_payment_status or "").strip() == "Unchecked"
            and (new_status or "").strip() == "Checked"
        ):
            raise HTTPException(
                status_code=403,
                detail="Pack can only change COD payment from Unchecked to Checked.",
            )

    has_alert = db.query(OrderAlert).filter(
        OrderAlert.order_id == order_id,
        OrderAlert.is_read == False
    ).first()

    if has_alert:
        raise HTTPException(
            status_code=400,
            detail="เปลี่ยนสถานะไม่ได้ เพราะมี Alert อยู่"
        )

    # 3️⃣ เปลี่ยน payment status
    payment.payment_status = new_status

    if new_status == "Paid":
        if not paid_date:
            raise HTTPException(
                status_code=400,
                detail="กรุณาระบุวันที่เงินเข้า"
            )

        payment.paid_date = paid_date
        payment.paid_note = paid_note

    else:
        # ถ้าเปลี่ยนเป็นสถานะอื่น เคลียร์ออก
        payment.paid_date = None
        payment.paid_note = None

    # 4️⃣ ดึง order
    order = db.query(Order).filter(Order.id == order_id).first()

    old_order_status = order.order_status

    # 5️⃣ 🔁 Sync order status (Special when payment Checked + shipping_method Special)
    sync_order_status_with_payment(order, new_status, getattr(order, "shipping_method", None))

    # 5b. Auto-set tracking number for Special orders
    if order.order_status == "Special":
        order.tracking_number = "Special"

    # 6️⃣ Log การเปลี่ยน Payment
    log_order_change(
        db=db,
        order_id=order.id,
        action="CHANGE_PAYMENT_STATUS",
        old_value=old_payment_status,
        new_value=new_status,
        user_id=user["user_id"]
    )

    # 7️⃣ Log การเปลี่ยน Order (ถ้ามี)
    if old_order_status != order.order_status:
        log_order_change(
            db=db,
            order_id=order.id,
            action="SYNC_ORDER_STATUS",
            old_value=old_order_status,
            new_value=order.order_status,
            user_id=user["user_id"]
        )

    # 7b. When order first becomes Checked or Special, lock net total for product-edit rule
    if order.order_status in ("Checked", "Special") and order.net_total_at_check is None:
        order.net_total_at_check = _order_net_total(db, order.id)

    # 8️⃣ commit ทีเดียว
    db.commit()

    return {
        "payment_status": payment.payment_status,
        "order_status": order.order_status
    }


@router.put("/{order_id}/status")
def update_order_status(
    order_id: int,
    new_status: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # 1️⃣ เช็ค role (Pack / Manager เท่านั้น)
    if user["role"] not in ["pack", "manager"]:
        raise HTTPException(
            status_code=403,
            detail="Only packing team can change order status"
        )

    # Block status change only when there are unread alerts targeting the current role (e.g. pack). Sale-only alerts (e.g. INVOICE_SUBMITTED) do not block pack. Manager can override.
    if user["role"] != "manager":
        has_unread_alert_for_me = db.query(OrderAlert).filter(
            OrderAlert.order_id == order_id,
            OrderAlert.is_read == False,
            OrderAlert.target_role == user["role"]
        ).first()
        if has_unread_alert_for_me:
            raise HTTPException(
                status_code=400,
                detail="กรุณารับทราบ Alert ทั้งหมดก่อนเปลี่ยนสถานะออเดอร์ (กด Acknowledge ใน Section 1)"
            )

    # 2️⃣ ดึง order + payment
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    payment = db.query(OrderPayment).filter(OrderPayment.order_id == order_id).first()

    # 2b. Pack cannot change status for Special orders (shipping method Special)
    if user["role"] == "pack" and (order.order_status or "") == "Special":
        raise HTTPException(
            status_code=403,
            detail="This order is Special (shipping method). Packing team cannot change order status.",
        )

    old_status = order.order_status

    # 3️⃣ เช็คว่าเปลี่ยนตาม flow ได้ไหม
    if not can_change_order_status(old_status, new_status):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot change order status from {old_status} to {new_status}"
        )
    
    # (Unread-alert check already done above: no status change until all alerts acknowledged)


    # 4️⃣ เปลี่ยนสถานะ
    order.order_status = new_status

    # 4b. When order first becomes Checked, lock net total for product-edit rule
    if new_status == "Checked" and order.net_total_at_check is None:
        order.net_total_at_check = _order_net_total(db, order.id)

    # 5️⃣ Log การเปลี่ยน
    log_order_change(
        db=db,
        order_id=order.id,
        action="CHANGE_ORDER_STATUS",
        old_value=old_status,
        new_value=new_status,
        user_id=user["user_id"]
    )

    # 6️⃣ commit
    db.commit()

    return {
        "order_id": order.id,
        "old_status": old_status,
        "new_status": new_status
    }


@router.put("/{order_id}/tracking-number")
def update_tracking_number(
    order_id: int,
    tracking_number: str | None = Body(default=None, embed=True),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user, ["pack", "manager"])
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    old_val = getattr(order, "tracking_number", None) or ""
    new_val = (tracking_number or "").strip() or None
    order.tracking_number = new_val
    log_order_change(
        db=db,
        order_id=order.id,
        action="UPDATE_TRACKING_NUMBER",
        old_value=old_val,
        new_value=new_val or "",
        user_id=user["user_id"],
    )
    db.commit()
    return {"order_id": order.id, "tracking_number": new_val}


@router.get("/alerts")
def get_my_alerts(limit: int = 20,
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    alerts = (
        db.query(OrderAlert)
        .filter(
            OrderAlert.target_role == user["role"],
            OrderAlert.is_read == False
        )
        .order_by(OrderAlert.created_at.desc())
        .limit(limit)
        .all()
    )

    return alerts



@router.put("/alerts/{alert_id}/read")
def mark_alert_read(
    alert_id: int,
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    alert = db.query(OrderAlert).filter(OrderAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.is_read = True
    db.commit()

    return {"message": "Alert marked as read"}


@router.put("/{order_id}/shipping-date")
def update_shipping_date(
    order_id: int,
    new_shipping_date: date | None = None,
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # 1️⃣ ดึง Order
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # 2️⃣ 🔒 เช็คกฎ (Sale แก้ได้เฉพาะก่อน Packing)
    if not can_edit_shipping_address(user["role"], order.order_status):
        raise HTTPException(
            status_code=403,
            detail="Cannot edit shipping date in current order status"
        )

    # 3️⃣ เก็บค่าเดิม
    old_date = order.shipping_date

    # 4️⃣ แก้ค่าใหม่
    order.shipping_date = new_shipping_date

    # 5️⃣ Log การเปลี่ยน
    log_order_change(
        db=db,
        order_id=order.id,
        action="UPDATE_SHIPPING_DATE",
        old_value=str(old_date) if old_date else "",
        new_value=str(new_shipping_date) if new_shipping_date else "",
        user_id=user["user_id"]
    )

    # 6️⃣ 🔔 สร้าง Alert ให้ Pack
    create_order_alert(
        db=db,
        order_id=order.id,
        alert_type="UPDATE_SHIPPING_DATE",
        message="มีการแก้ไขวันจัดส่งสินค้า",
        target_role="pack"
    )

    # 7️⃣ commit ทีเดียว
    db.commit()

    return {"message": "Shipping date updated"}


@router.put("/{order_id}/shipping-method")
def update_shipping_method(
    order_id: int,
    shipping_method: str = Query(..., description="Normal | Special"),
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    require_role(user, ["sale", "manager"])

    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if (order.order_status or "") == "Special":
        raise HTTPException(
            status_code=400,
            detail="Cannot change shipping method when order status is already Special.",
        )

    method_val = (shipping_method or "").strip()
    if method_val.lower() not in ("normal", "special"):
        raise HTTPException(status_code=400, detail="shipping_method must be Normal or Special")

    method_val = "Special" if method_val.lower() == "special" else "Normal"
    old_val = getattr(order, "shipping_method", None) or "Normal"

    if old_val == method_val:
        return {"message": "Shipping method unchanged", "shipping_method": method_val}

    order.shipping_method = method_val
    log_order_change(
        db=db,
        order_id=order.id,
        action="UPDATE_SHIPPING_METHOD",
        old_value=old_val,
        new_value=method_val,
        user_id=user["user_id"],
    )
    create_order_alert(
        db=db,
        order_id=order.id,
        alert_type="UPDATE_SHIPPING_METHOD",
        message="มีการแก้ไขวิธีจัดส่ง (Shipping method)",
        target_role="pack",
    )
    db.commit()
    return {"message": "Shipping method updated", "shipping_method": method_val}


@router.get("/alerts/count")
def get_my_alert_count(
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    count = (
        db.query(OrderAlert)
        .filter(
            OrderAlert.target_role == user["role"],
            OrderAlert.is_read == False
        )
        .count()
    )

    return {"count": count}


@router.get("/revenue-summary")
def get_revenue_summary(
    created_from: str | None = Query(None, description="YYYY-MM-DD"),
    created_to: str | None = Query(None, description="YYYY-MM-DD"),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Revenue by status bucket (by order created_at). Default: all time."""
    query = db.query(Order)
    if created_from:
        try:
            dt_from = datetime.strptime(created_from, "%Y-%m-%d").date()
            query = query.filter(func.date(Order.created_at) >= dt_from)
        except ValueError:
            pass
    if created_to:
        try:
            dt_to = datetime.strptime(created_to, "%Y-%m-%d").date()
            query = query.filter(func.date(Order.created_at) <= dt_to)
        except ValueError:
            pass
    orders = query.all()
    pending_revenue = 0.0
    checked_revenue = 0.0
    packing_shipping_revenue = 0.0
    success_revenue = 0.0
    fail_return_revenue = 0.0

    pending_product_count = 0
    checked_product_count = 0
    packing_shipping_product_count = 0
    success_product_count = 0
    fail_return_product_count = 0

    for order in orders:
        net = _order_net_total(db, order.id)
        # Count how many main products are on this order (each order item = 1 unit)
        item_count = db.query(OrderItem).filter(OrderItem.order_id == order.id).count()
        s = (order.order_status or "").strip()
        if s == "Pending":
            pending_revenue += net
            pending_product_count += item_count
        elif s == "Checked":
            checked_revenue += net
            checked_product_count += item_count
        elif s in ("Packing", "Shipped"):
            packing_shipping_revenue += net
            packing_shipping_product_count += item_count
        elif s == "Success":
            success_revenue += net
            success_product_count += item_count
        elif s in ("Fail", "Return Received"):
            fail_return_revenue += net
            fail_return_product_count += item_count

    total_revenue = (
        pending_revenue + checked_revenue + packing_shipping_revenue + success_revenue + fail_return_revenue
    )
    total_product_count = (
        pending_product_count
        + checked_product_count
        + packing_shipping_product_count
        + success_product_count
        + fail_return_product_count
    )

    return {
        "pending_revenue": round(pending_revenue, 2),
        "checked_revenue": round(checked_revenue, 2),
        "packing_shipping_revenue": round(packing_shipping_revenue, 2),
        "success_revenue": round(success_revenue, 2),
        "fail_return_revenue": round(fail_return_revenue, 2),
        "total_revenue": round(total_revenue, 2),
        "pending_product_count": pending_product_count,
        "checked_product_count": checked_product_count,
        "packing_shipping_product_count": packing_shipping_product_count,
        "success_product_count": success_product_count,
        "fail_return_product_count": fail_return_product_count,
        "total_product_count": total_product_count,
    }


@router.get("/revenue-by-date")
def get_revenue_by_date(
    created_from: str | None = Query(None, description="YYYY-MM-DD"),
    created_to: str | None = Query(None, description="YYYY-MM-DD"),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Revenue by day (by order created_at date). For dashboard chart. Returns list of { date, ...revenues }."""
    query = db.query(Order)
    if created_from:
        try:
            dt_from = datetime.strptime(created_from, "%Y-%m-%d").date()
            query = query.filter(func.date(Order.created_at) >= dt_from)
        except ValueError:
            pass
    if created_to:
        try:
            dt_to = datetime.strptime(created_to, "%Y-%m-%d").date()
            query = query.filter(func.date(Order.created_at) <= dt_to)
        except ValueError:
            pass
    orders = query.order_by(Order.created_at.asc()).all()
    # Group by date
    from collections import defaultdict
    daily = defaultdict(lambda: {
        "pending_revenue": 0.0,
        "checked_revenue": 0.0,
        "packing_shipping_revenue": 0.0,
        "success_revenue": 0.0,
        "fail_return_revenue": 0.0,
    })
    for order in orders:
        dt = order.created_at.date() if hasattr(order.created_at, "date") else order.created_at
        if hasattr(dt, "isoformat"):
            key = dt.isoformat()
        else:
            key = str(dt)[:10]
        net = _order_net_total(db, order.id)
        s = (order.order_status or "").strip()
        if s == "Pending":
            daily[key]["pending_revenue"] += net
        elif s == "Checked":
            daily[key]["checked_revenue"] += net
        elif s in ("Packing", "Shipped"):
            daily[key]["packing_shipping_revenue"] += net
        elif s == "Success":
            daily[key]["success_revenue"] += net
        elif s in ("Fail", "Return Received"):
            daily[key]["fail_return_revenue"] += net
    # Determine full date range: use filter params if set, else min/max from data
    if created_from and created_to:
        try:
            start = datetime.strptime(created_from, "%Y-%m-%d").date()
            end = datetime.strptime(created_to, "%Y-%m-%d").date()
        except ValueError:
            start = min(daily.keys()) if daily else date.today()
            end = max(daily.keys()) if daily else date.today()
    elif daily:
        start = min(datetime.strptime(d, "%Y-%m-%d").date() for d in daily.keys())
        end = max(datetime.strptime(d, "%Y-%m-%d").date() for d in daily.keys())
    else:
        start = end = date.today()
    if start > end:
        start, end = end, start
    # Build one entry per day in range
    out = []
    current = start
    while current <= end:
        date_str = current.isoformat()
        row = daily.get(date_str, {
            "pending_revenue": 0.0,
            "checked_revenue": 0.0,
            "packing_shipping_revenue": 0.0,
            "success_revenue": 0.0,
            "fail_return_revenue": 0.0,
        })
        total = (
            row["pending_revenue"] + row["checked_revenue"] + row["packing_shipping_revenue"]
            + row["success_revenue"] + row["fail_return_revenue"]
        )
        out.append({
            "date": date_str,
            "pending_revenue": round(row["pending_revenue"], 2),
            "checked_revenue": round(row["checked_revenue"], 2),
            "packing_shipping_revenue": round(row["packing_shipping_revenue"], 2),
            "success_revenue": round(row["success_revenue"], 2),
            "fail_return_revenue": round(row["fail_return_revenue"], 2),
            "total_revenue": round(total, 2),
        })
        current += timedelta(days=1)
    return {"series": out}


@router.get("/revenue-by-product")
def get_revenue_by_product(
    created_from: str | None = Query(None, description="YYYY-MM-DD"),
    created_to: str | None = Query(None, description="YYYY-MM-DD"),
    group_by: str = Query("category", description="category | product_name"),
    sale_id: int | None = Query(
        None,
        description="Optional sale id to filter by (sale role is always limited to own id).",
    ),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Revenue by product category or by product name (order item level, filtered by order created_at and optional sale)."""
    # Allow only relevant roles to use this endpoint
    require_role(user, ["sale", "manager", "account"])

    role = user.get("role")
    current_sale_id = user.get("user_id")

    # Determine effective sale filter
    effective_sale_id: int | None = None
    if role == "sale" and current_sale_id is not None:
        # Sale can only see their own data; ignore query param
        effective_sale_id = int(current_sale_id)
    elif role in ("manager", "account") and sale_id is not None:
        effective_sale_id = int(sale_id)

    query = db.query(Order)
    if created_from:
        try:
            dt_from = datetime.strptime(created_from, "%Y-%m-%d").date()
            query = query.filter(func.date(Order.created_at) >= dt_from)
        except ValueError:
            pass
    if created_to:
        try:
            dt_to = datetime.strptime(created_to, "%Y-%m-%d").date()
            query = query.filter(func.date(Order.created_at) <= dt_to)
        except ValueError:
            pass
    if effective_sale_id is not None:
        query = query.filter(Order.sale_id == effective_sale_id)
    order_ids = [o.id for o in query.all()]
    if not order_ids:
        return {"items": []}
    # Item-level revenue: sum(unit_price - discount) per order item
    if (group_by or "category").strip().lower() == "product_name":
        # Group by product name (snapshot on order item)
        rows = (
            db.query(
                OrderItem.product_name,
                (func.sum(OrderItem.unit_price - OrderItem.discount)).label("revenue"),
                func.count(OrderItem.id).label("pcs"),
            )
            .filter(OrderItem.order_id.in_(order_ids))
            .group_by(OrderItem.product_name)
            .all()
        )
        items = [
            {
                "name": (r.product_name or "—") or "—",
                "revenue": round(float(r.revenue or 0), 2),
                "pcs": int(r.pcs or 0),
            }
            for r in rows
        ]
    else:
        # Group by product category (join Product)
        rows = (
            db.query(
                Product.category,
                (func.sum(OrderItem.unit_price - OrderItem.discount)).label("revenue"),
                func.count(OrderItem.id).label("pcs"),
            )
            .join(OrderItem, OrderItem.product_id == Product.id)
            .filter(OrderItem.order_id.in_(order_ids))
            .group_by(Product.category)
            .all()
        )
        items = [
            {
                "name": (r.category or "—") or "—",
                "revenue": round(float(r.revenue or 0), 2),
                "pcs": int(r.pcs or 0),
            }
            for r in rows
        ]
    return {"items": items}


@router.get("/revenue-by-payment-method")
def get_revenue_by_payment_method(
    created_from: str | None = Query(None, description="YYYY-MM-DD"),
    created_to: str | None = Query(None, description="YYYY-MM-DD"),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Revenue by payment method (for dashboard). Manager/account only."""
    require_role(user, ["manager", "account"])

    query = (
        db.query(
            OrderPayment.payment_method.label("payment_method"),
            (func.sum(OrderItem.unit_price - OrderItem.discount)).label("revenue"),
        )
        .join(Order, Order.id == OrderPayment.order_id)
        .join(OrderItem, OrderItem.order_id == Order.id)
    )
    if created_from:
        try:
            dt_from = datetime.strptime(created_from, "%Y-%m-%d").date()
            query = query.filter(func.date(Order.created_at) >= dt_from)
        except ValueError:
            pass
    if created_to:
        try:
            dt_to = datetime.strptime(created_to, "%Y-%m-%d").date()
            query = query.filter(func.date(Order.created_at) <= dt_to)
        except ValueError:
            pass
    rows = query.group_by(OrderPayment.payment_method).all()
    items = [
        {"name": (r.payment_method or "—") or "—", "revenue": round(float(r.revenue or 0), 2)}
        for r in rows
    ]
    return {"items": items}


@router.get("/revenue-by-sale")
def get_revenue_by_sale(
    created_from: str | None = Query(None, description="YYYY-MM-DD"),
    created_to: str | None = Query(None, description="YYYY-MM-DD"),
    sale_id: int | None = Query(
        None,
        description="Optional: filter by specific sale id (manager/account only)",
    ),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Revenue by sale name (order creator).

    - Sale role: always restricted to current user (cannot see others).
    - Manager / Accountant: can see all, or filter to a specific sale_id.
    """
    # Allow only relevant roles to use this endpoint
    require_role(user, ["sale", "manager", "account"])

    query = (
        db.query(
            User.name,
            (func.sum(OrderItem.unit_price - OrderItem.discount)).label("revenue"),
            func.count(func.distinct(Order.id)).label("order_count"),
            Order.sale_id.label("sale_id"),
        )
        .join(Order, Order.sale_id == User.id)
        .join(OrderItem, OrderItem.order_id == Order.id)
    )

    role = user.get("role")
    current_sale_id = user.get("user_id")

    # Sale can only see their own revenue
    if role == "sale" and current_sale_id is not None:
        query = query.filter(Order.sale_id == current_sale_id)
    # Manager / accountant can optionally filter by a specific sale_id
    elif role in ("manager", "account") and sale_id is not None:
        query = query.filter(Order.sale_id == sale_id)

    if created_from:
        try:
            dt_from = datetime.strptime(created_from, "%Y-%m-%d").date()
            query = query.filter(func.date(Order.created_at) >= dt_from)
        except ValueError:
            pass
    if created_to:
        try:
            dt_to = datetime.strptime(created_to, "%Y-%m-%d").date()
            query = query.filter(func.date(Order.created_at) <= dt_to)
        except ValueError:
            pass
    rows = query.group_by(Order.sale_id, User.name).all()
    items = [
        {
            "sale_id": r.sale_id,
            "name": (r.name or "—") or "—",
            "revenue": round(float(r.revenue or 0), 2),
            "order_count": int(r.order_count or 0),
        }
        for r in rows
    ]
    return {"items": items}


@router.get("/revenue-by-sale-breakdown")
def get_revenue_by_sale_breakdown(
    created_from: str | None = Query(None, description="YYYY-MM-DD"),
    created_to: str | None = Query(None, description="YYYY-MM-DD"),
    sale_id: int | None = Query(
        None,
        description="Sale id to focus on (ignored for sale role, required for manager/account).",
    ),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Breakdown revenue for a single sale by product category, pageName, and status."""

    require_role(user, ["sale", "manager", "account"])

    role = user.get("role")
    current_sale_id = user.get("user_id")

    # Determine which sale we are allowed to see
    effective_sale_id: int | None = None
    if role == "sale" and current_sale_id is not None:
        # Sale can only see their own breakdown; ignore query param
        effective_sale_id = int(current_sale_id)
    elif role in ("manager", "account") and sale_id is not None:
        effective_sale_id = int(sale_id)

    # Sale role must have a sale id; manager/account may omit sale_id = all sales in range
    if effective_sale_id is None and role == "sale":
        return {"categories": [], "pages": [], "statuses": [], "shipping_methods": []}

    # Build common filters (optional sale + created_at range)
    filters: list = []
    if effective_sale_id is not None:
        filters.append(Order.sale_id == effective_sale_id)
    if created_from:
        try:
            dt_from = datetime.strptime(created_from, "%Y-%m-%d").date()
            filters.append(func.date(Order.created_at) >= dt_from)
        except ValueError:
            pass
    if created_to:
        try:
            dt_to = datetime.strptime(created_to, "%Y-%m-%d").date()
            filters.append(func.date(Order.created_at) <= dt_to)
        except ValueError:
            pass

    # Breakdown by product category
    cat_rows = (
        db.query(
            Product.category.label("category"),
            (func.sum(OrderItem.unit_price - OrderItem.discount)).label("revenue"),
            func.count(OrderItem.id).label("pcs"),
        )
        .join(OrderItem, OrderItem.product_id == Product.id)
        .join(Order, Order.id == OrderItem.order_id)
        .filter(*filters)
        .group_by(Product.category)
        .all()
    )
    categories = [
        {
            "name": (r.category or "—") or "—",
            "revenue": round(float(r.revenue or 0), 2),
            "pcs": int(r.pcs or 0),
        }
        for r in cat_rows
    ]

    # Breakdown by pageName
    page_rows = (
        db.query(
            Order.pageName.label("page_name"),
            (func.sum(OrderItem.unit_price - OrderItem.discount)).label("revenue"),
            func.count(OrderItem.id).label("pcs"),
        )
        .join(OrderItem, OrderItem.order_id == Order.id)
        .filter(*filters)
        .group_by(Order.pageName)
        .all()
    )
    pages = [
        {
            "name": (r.page_name or "—") or "—",
            "revenue": round(float(r.revenue or 0), 2),
            "pcs": int(r.pcs or 0),
        }
        for r in page_rows
    ]

    # Breakdown by order status
    status_rows = (
        db.query(
            Order.order_status.label("status"),
            (func.sum(OrderItem.unit_price - OrderItem.discount)).label("revenue"),
            func.count(func.distinct(Order.id)).label("order_count"),
        )
        .join(OrderItem, OrderItem.order_id == Order.id)
        .filter(*filters)
        .group_by(Order.order_status)
        .all()
    )
    statuses = [
        {
            "status": (r.status or "—") or "—",
            "revenue": round(float(r.revenue or 0), 2),
            "order_count": int(r.order_count or 0),
        }
        for r in status_rows
    ]

    # Breakdown by shipping method
    ship_rows = (
        db.query(
            func.coalesce(Order.shipping_method, "Normal").label("shipping_method"),
            (func.sum(OrderItem.unit_price - OrderItem.discount)).label("revenue"),
        )
        .join(OrderItem, OrderItem.order_id == Order.id)
        .filter(*filters)
        .group_by(func.coalesce(Order.shipping_method, "Normal"))
        .all()
    )
    shipping_methods = [
        {
            "name": (r.shipping_method or "Normal") or "Normal",
            "revenue": round(float(r.revenue or 0), 2),
        }
        for r in ship_rows
    ]

    return {"categories": categories, "pages": pages, "statuses": statuses, "shipping_methods": shipping_methods}


@router.get("")
def list_orders(
    order_status: str | None = None,
    order_status_in: list[str] | None = Query(None),  # multi: e.g. ?order_status_in=Shipped&order_status_in=Success
    payment_status: str | None = None,
    has_alert: bool | None = None,
    keyword: str | None = None,
    sort_by: str | None = None,
    only_my: bool | None = None,
    shipping_date: str | None = None,  # YYYY-MM-DD
    payment_method: list[str] | None = Query(None),  # multi: cod, transfer, card_2c2p, card_pay
    product_category: list[str] | None = Query(None),  # multi: order has item in any of these categories
    invoice_required: bool | None = None,  # True: only orders that require invoice
    has_invoice_file: bool | None = None,  # True: has invoice/invoice_submit file; False: no such file
    has_tracking_number: bool | None = None,  # False: only orders without tracking number (for Tracking Number page)
    exclude_payment_method: str | None = None,
    shipping_method: str | None = None,  # e.g. "Normal" for Packing/Tracking pages
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(50, ge=1, le=100, description="Rows per page (max 100)"),
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):

    # 1️⃣ เริ่มจาก join Order + Payment ก่อน
    query = (
        db.query(Order, OrderPayment)
        .join(OrderPayment, OrderPayment.order_id == Order.id)
    )

    # 2️⃣ Filter: Order Status (single or multi)
    if order_status_in and len(order_status_in) > 0:
        query = query.filter(Order.order_status.in_(order_status_in))
    elif order_status:
        query = query.filter(Order.order_status == order_status)

    # 2b. Filter: Shipping date (e.g. for pack shortcut "today", format YYYY-MM-DD)
    if shipping_date:
        try:
            sd = datetime.strptime(shipping_date, "%Y-%m-%d").date()
            query = query.filter(Order.shipping_date == sd)
        except ValueError:
            pass

    # 3️⃣ Filter: Payment Status
    if payment_status:
        query = query.filter(
            OrderPayment.payment_status == payment_status
        )

    # 3b. Filter: Payment method (multi)
    if payment_method and len(payment_method) > 0:
        query = query.filter(OrderPayment.payment_method.in_(payment_method))

    # 3b2. Exclude a payment method
    if exclude_payment_method:
        query = query.filter(OrderPayment.payment_method != exclude_payment_method)

    # 3c. Filter: Product category (multi: order has at least one item in any of these categories)
    if product_category and len(product_category) > 0:
        order_ids_subq = (
            db.query(OrderItem.order_id)
            .join(Product, Product.id == OrderItem.product_id)
            .filter(Product.category.in_(product_category))
            .distinct()
            .subquery()
        )
        query = query.filter(Order.id.in_(order_ids_subq))

    # 4️⃣ Filter: มี Alert ค้างไหม
    if has_alert:
        query = query.join(
            OrderAlert,
            OrderAlert.order_id == Order.id
        ).filter(OrderAlert.is_read == False)

    # 5️⃣ Filter: Only my orders (สำหรับ Sale)
    if only_my and user["role"] == "sale":
        query = query.filter(Order.sale_id == user["user_id"])

    # 5b. Filter: Invoice submit page (orders that require invoice; with/without invoice file)
    if invoice_required is True:
        query = query.filter(Order.invoice_required == True)
    # has_invoice_file: only invoice_submit counts (complete invoice returned by account/manager). Sale's "invoice" on create is just address picture.
    if has_invoice_file is not None:
        order_ids_with_invoice = (
            db.query(OrderFile.order_id)
            .filter(OrderFile.file_type == "invoice_submit")
            .distinct()
            .subquery()
        )
        if has_invoice_file:
            query = query.filter(Order.id.in_(order_ids_with_invoice))
        else:
            query = query.filter(~Order.id.in_(order_ids_with_invoice))

    # 5c. Filter: Tracking Number page — only orders without a tracking number
    if has_tracking_number is False:
        query = query.filter(
            (Order.tracking_number.is_(None)) | (func.coalesce(func.trim(Order.tracking_number), "") == "")
        )

    # 5d. Filter: Shipping method (e.g. Packing/Tracking pages show only Normal)
    if shipping_method:
        query = query.filter(func.coalesce(Order.shipping_method, "Normal") == shipping_method)

    # 6️⃣ Search (order ID, customer name/phone, tracking number, sale name)
    if keyword:
        kw = f"%{keyword}%"
        query = query.outerjoin(User, Order.sale_id == User.id)
        query = query.filter(
            Order.order_code.ilike(kw)
            | Order.customer_name.ilike(kw)
            | Order.customer_phone.ilike(kw)
            | Order.tracking_number.ilike(kw)
            | User.name.ilike(kw)
        )

    # 7️⃣ Total (distinct order ids — some joins can duplicate Order rows)
    count_subq = query.with_entities(Order.id).distinct().subquery()
    total = db.query(func.count()).select_from(count_subq).scalar() or 0

    # 8️⃣ Sorting + pagination
    if sort_by == "oldest":
        query = query.order_by(Order.created_at.asc())
    else:
        query = query.order_by(Order.created_at.desc())

    orders = (
        query.offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    order_ids = [o.id for o, _ in orders]
    sale_ids = list({o.sale_id for o, _ in orders if o.sale_id})
    sale_names = {}
    if sale_ids:
        for uid, uname in db.query(User.id, User.name).filter(User.id.in_(sale_ids)).all():
            sale_names[uid] = uname or ""

    if order_ids:
        items = (
            db.query(OrderItem.order_id, OrderItem.product_name)
            .filter(OrderItem.order_id.in_(order_ids))
            .order_by(OrderItem.order_id, OrderItem.id)
            .all()
        )
    else:
        items = []
    first_product_by_order = {}
    for oid, pname in items:
        if oid not in first_product_by_order:
            first_product_by_order[oid] = pname

    if order_ids:
        order_ids_with_invoice_submitted = set(
            oid for (oid,) in db.query(OrderFile.order_id)
            .filter(OrderFile.order_id.in_(order_ids), OrderFile.file_type == "invoice_submit")
            .distinct()
            .all()
        )

        invoice_submit_rows = (
            db.query(OrderFile.order_id, OrderFile.file_url)
            .filter(OrderFile.order_id.in_(order_ids), OrderFile.file_type == "invoice_submit")
            .order_by(OrderFile.order_id, OrderFile.id)
            .all()
        )
    else:
        order_ids_with_invoice_submitted = set()
        invoice_submit_rows = []

    invoice_submit_url_by_order = {}
    for oid, url in invoice_submit_rows:
        if oid not in invoice_submit_url_by_order:
            invoice_submit_url_by_order[oid] = url

    result = []

    unread_order_ids: set[int] = set()
    if order_ids:
        unread_order_ids = {
            oid
            for (oid,) in db.query(OrderAlert.order_id)
            .filter(OrderAlert.order_id.in_(order_ids), OrderAlert.is_read == False)
            .distinct()
            .all()
        }

    for order, payment in orders:
        has_unread_alert = order.id in unread_order_ids

        has_invoice_submitted = order.id in order_ids_with_invoice_submitted
        invoice_submit_file_url = invoice_submit_url_by_order.get(order.id)

        result.append({
            "id": order.id,
            "order_code": order.order_code,
            "order_status": order.order_status,
            "tracking_number": getattr(order, "tracking_number", None) or None,
            "shipping_method": getattr(order, "shipping_method", None) or "Normal",
            "payment_status": payment.payment_status,
            "payment_method": payment.payment_method,
            "customer_name": order.customer_name,
            "customer_phone": order.customer_phone,
            "shipping_date": order.shipping_date,
            "shipping_note": order.shipping_note,
            "pageName": order.pageName,
            "sale_id": order.sale_id,
            "sale_name": sale_names.get(order.sale_id) if order.sale_id else None,
            "invoice_number": getattr(order, "invoice_number", None),
            "has_unread_alert": has_unread_alert,
            "has_invoice_submitted": has_invoice_submitted,
            "invoice_submit_file_url": invoice_submit_file_url,
            "main_product_name": first_product_by_order.get(order.id),
        })

    return {"items": result, "total": total, "page": page, "page_size": page_size}




@router.get("/{order_id}")
def get_order_detail(
    order_id: int,
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Order Detail View
    - ใช้ได้ทุก Role
    - รวมข้อมูลทั้งหมดในหน้าเดียว
    """

    # 1️⃣ ดึง Order
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # 2️⃣ ดึง Payment
    payment = db.query(OrderPayment).filter(
        OrderPayment.order_id == order.id
    ).first()

    # 3️⃣ ดึง Files (chat / slip / invoice / return)
    files = (
        db.query(OrderFile)
        .filter(OrderFile.order_id == order.id)
        .all()
    )

    # 4️⃣ ดึง Logs (Timeline)
    logs = (
        db.query(OrderLog)
        .filter(OrderLog.order_id == order.id)
        .order_by(OrderLog.performed_at.asc())
        .all()
    )

    # 5️⃣ ดึง Alerts ที่ยังไม่อ่าน (ของ order นี้)
    alerts = (
        db.query(OrderAlert)
        .filter(
            OrderAlert.order_id == order.id,
            OrderAlert.is_read == False
        )
        .all()
    )

    items = (
        db.query(OrderItem)
        .filter(OrderItem.order_id == order.id)
        .all()
    )

    net_total = 0
    items_data = []
    for item in items:
        net_total += float(item.unit_price) - float(item.discount)
        item_freebies = (
            db.query(OrderItemFreebie)
            .filter(OrderItemFreebie.order_item_id == item.id)
            .all()
        )
        freebies_data = []
        for oif in item_freebies:
            freebie = db.query(Freebie).filter(Freebie.id == oif.freebie_id).first()
            freebies_data.append({
                "id": oif.id,
                "freebie_id": oif.freebie_id,
                "freebie_name": freebie.name if freebie else None,
            })
        items_data.append({
            "id": item.id,
            "order_id": item.order_id,
            "product_id": item.product_id,
            "product_name": item.product_name,
            "unit_price": float(item.unit_price),
            "discount": float(item.discount),
            "freebies": freebies_data,
        })

    # Explicit order dict so shipping_note and all fields are always included
    sale_name = None
    if order.sale_id:
        u = db.query(User).filter(User.id == order.sale_id).first()
        sale_name = (u.name or "").strip() or None if u else None
    order_data = {
        "id": order.id,
        "order_code": order.order_code,
        "sale_id": order.sale_id,
        "sale_name": sale_name,
        "customer_name": order.customer_name,
        "customer_phone": order.customer_phone,
        "shipping_address_text": order.shipping_address_text,
        "shipping_note": order.shipping_note,
        "shipping_date": str(order.shipping_date) if order.shipping_date else None,
        "order_status": order.order_status,
        "tracking_number": getattr(order, "tracking_number", None) or None,
        "shipping_method": getattr(order, "shipping_method", None) or "Normal",
        "payment_status": order.payment_status,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "pageName": order.pageName,
        "note": order.note,
        "invoice_required": getattr(order, "invoice_required", False),
        "invoice_text": order.invoice_text,
        "invoice_number": getattr(order, "invoice_number", None),
    }

    payment_data = None
    if payment:
        _pd = payment.paid_date
        paid_date_str = None
        if _pd is not None:
            paid_date_str = getattr(_pd, "isoformat", lambda: str(_pd))()
            if paid_date_str and len(paid_date_str) > 10:
                paid_date_str = paid_date_str[:10]  # date only for frontend
        payment_data = {
            "payment_method": payment.payment_method,
            "payment_status": payment.payment_status,
            "paid_date": paid_date_str,
            "paid_note": payment.paid_note,
            "installment_type": payment.installment_type,
            "installment_months": payment.installment_months,
        }

    # Order-level freebies (from POST /orders/{id}/freebies during create)
    order_freebies_rows = (
        db.query(OrderFreebie)
        .filter(OrderFreebie.order_id == order.id)
        .all()
    )
    order_freebies_data = []
    for of in order_freebies_rows:
        freebie = db.query(Freebie).filter(Freebie.id == of.freebie_id).first()
        order_freebies_data.append({
            "id": of.id,
            "freebie_id": of.freebie_id,
            "freebie_name": freebie.name if freebie else None,
        })

    files_data = [{"id": f.id, "file_type": f.file_type, "file_url": f.file_url} for f in files]
    alerts_data = [{"id": a.id, "message": a.message, "is_read": a.is_read, "target_role": a.target_role} for a in alerts]
    logs_data = [{"id": l.id, "action": l.action, "old_value": l.old_value, "new_value": l.new_value, "performed_at": l.performed_at.isoformat() if getattr(l.performed_at, "isoformat", None) else str(l.performed_at)} for l in logs]

    net_at_check = None
    if getattr(order, "net_total_at_check", None) is not None:
        net_at_check = float(order.net_total_at_check)
    product_editable = can_edit_product(
        user["role"], order.order_status, net_total=net_total, net_total_at_check=net_at_check
    )

    return {
        "order": order_data,
        "payment": payment_data,
        "items": items_data,
        "order_freebies": order_freebies_data,
        "net_total": net_total,
        "product_editable": product_editable,
        "files": files_data,
        "logs": logs_data,
        "alerts": alerts_data,
    }


@router.delete("/{order_id_or_code}")
def delete_order(
    order_id_or_code: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Manager only. Permanently delete an order and all related data. Accepts numeric order ID or order code (e.g. SG-26-03-08-00001)."""
    require_role(user, ["manager"])
    order = None
    if order_id_or_code.isdigit():
        order = db.query(Order).filter(Order.id == int(order_id_or_code)).first()
    if not order:
        order = db.query(Order).filter(Order.order_code == order_id_or_code).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    order_id = order.id
    # Delete in dependency order: item freebies -> order items -> order freebies -> files, logs, alerts -> payment -> order
    order_item_ids = [r[0] for r in db.query(OrderItem.id).filter(OrderItem.order_id == order_id).all()]
    if order_item_ids:
        db.query(OrderItemFreebie).filter(OrderItemFreebie.order_item_id.in_(order_item_ids)).delete(synchronize_session=False)
    db.query(OrderItem).filter(OrderItem.order_id == order_id).delete(synchronize_session=False)
    db.query(OrderFreebie).filter(OrderFreebie.order_id == order_id).delete(synchronize_session=False)
    db.query(OrderFile).filter(OrderFile.order_id == order_id).delete(synchronize_session=False)
    db.query(OrderLog).filter(OrderLog.order_id == order_id).delete(synchronize_session=False)
    db.query(OrderAlert).filter(OrderAlert.order_id == order_id).delete(synchronize_session=False)
    db.query(OrderPayment).filter(OrderPayment.order_id == order_id).delete(synchronize_session=False)
    db.delete(order)
    db.commit()
    return {"message": "Order and all related data deleted", "order_id": order_id, "order_code": order_id_or_code}


@router.post("/{order_id}/items")
def add_order_item(
    order_id: int,
    product_id: int,
    discount: float = 0,
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Sale / Manager เท่านั้น
    if user["role"] not in ["sale", "manager"]:
        raise HTTPException(status_code=403, detail="Permission denied")

    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    current_net = _order_net_total(db, order.id)
    net_at_check = float(order.net_total_at_check) if getattr(order, "net_total_at_check", None) is not None else None
    if not can_edit_product(
        user["role"], order.order_status, net_total=current_net, net_total_at_check=net_at_check
    ):
        raise HTTPException(
            status_code=403,
            detail="Main product cannot be edited: order is Shipped or later, or (Checked/Packing) net total has changed.",
        )

    product = db.query(Product).filter(
        Product.id == product_id,
        Product.is_active == True
    ).first()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    new_item_net = float(product.price) - float(discount)
    if order.order_status in ("Checked", "Packing") and net_at_check is not None:
        new_net_after = current_net + new_item_net
        if abs(new_net_after - net_at_check) >= 0.01:
            raise HTTPException(
                status_code=400,
                detail="In Checked/Packing, product changes must keep the same net total.",
            )

    item = OrderItem(
        order_id=order.id,
        product_id=product.id,
        product_name=product.name,
        unit_price=product.price,
        discount=discount
    )

    db.add(item)
    db.commit()
    db.refresh(item)

    return {
        "message": "Product added to order",
        "order_item_id": item.id
    }


@router.put("/items/{order_item_id}")
def update_order_item_product(
    order_item_id: int,
    product_id: int,
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Change an order item's product. If new price differs, reset order status to Pending and payment to Unchecked."""
    if user["role"] not in ["sale", "manager"]:
        raise HTTPException(status_code=403, detail="Permission denied")

    item = db.query(OrderItem).filter(OrderItem.id == order_item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Order item not found")

    order = db.query(Order).filter(Order.id == item.order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    current_net = _order_net_total(db, order.id)
    net_at_check = float(order.net_total_at_check) if getattr(order, "net_total_at_check", None) is not None else None
    if not can_edit_product(
        user["role"], order.order_status, net_total=current_net, net_total_at_check=net_at_check
    ):
        raise HTTPException(
            status_code=403,
            detail="Main product cannot be edited: order is Shipped or later, or (Checked/Packing) net total has changed.",
        )

    new_product = db.query(Product).filter(
        Product.id == product_id,
        Product.is_active == True
    ).first()
    if not new_product:
        raise HTTPException(status_code=404, detail="Product not found")

    current_unit_price = float(item.unit_price)
    new_price = float(new_product.price)
    price_changed = abs(new_price - current_unit_price) >= 0.01

    old_discount = float(item.discount)
    # Keep the same discount % when changing product (or keep 1000 baht flat)
    if current_unit_price >= 0.01 and new_price >= 0.01:
        if 999 <= old_discount <= 1001:
            new_discount = 1000.0
        else:
            ratio = old_discount / current_unit_price
            new_discount = round(ratio * new_price, 2)
        item.discount = new_discount
    # else leave discount as-is

    old_product_name = item.product_name
    item.product_id = new_product.id
    item.product_name = new_product.name
    item.unit_price = new_product.price

    # If price changed: reset order status to Pending and payment status to Unchecked
    if price_changed:
        order.order_status = "Pending"
        order.net_total_at_check = None
        payment = db.query(OrderPayment).filter(OrderPayment.order_id == order.id).first()
        if payment:
            payment.payment_status = "Unchecked"
            payment.paid_date = None
            payment.paid_note = None

    create_order_alert(
        db=db,
        order_id=order.id,
        alert_type="PRODUCT_CHANGED",
        message=f"สินค้าหลักเปลี่ยนจาก {old_product_name} เป็น {new_product.name}",
        target_role="pack",
    )

    db.commit()
    db.refresh(item)
    return {"message": "Order item product updated", "order_item_id": item.id}


@router.put("/items/{order_item_id}/discount")
def update_order_item_discount(
    order_item_id: int,
    discount: float = 0,
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update order item discount. Editable only when order status is Pending. Creates alert when changed."""
    if user["role"] not in ["sale", "manager"]:
        raise HTTPException(status_code=403, detail="Permission denied")

    item = db.query(OrderItem).filter(OrderItem.id == order_item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Order item not found")

    order = db.query(Order).filter(Order.id == item.order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.order_status != "Pending":
        raise HTTPException(
            status_code=403,
            detail="Discount can only be edited when order status is Pending.",
        )

    discount = max(0, float(discount))
    old_discount = float(item.discount)
    if abs(discount - old_discount) < 0.01:
        return {"message": "No change", "order_item_id": item.id}

    item.discount = discount
    create_order_alert(
        db=db,
        order_id=order.id,
        alert_type="UPDATE_ITEM_DISCOUNT",
        message=f"มีการแก้ไขส่วนลดสินค้า {item.product_name}",
        target_role="pack",
    )
    db.commit()
    db.refresh(item)
    return {"message": "Order item discount updated", "order_item_id": item.id}


@router.post("/items/{order_item_id}/freebies")
def add_order_item_freebie(
    order_item_id: int,
    freebie_name: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if user["role"] not in ["sale", "manager"]:
        raise HTTPException(status_code=403, detail="Permission denied")

    freebie = OrderItemFreebie(
        order_item_id=order_item_id,
        freebie_name=freebie_name
    )

    db.add(freebie)
    db.commit()

    return {"message": "Freebie added to order item"}


@router.get("/dashboard/kpi")
def get_dashboard_kpi(
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):

    today = date.today()

    # Orders Today
    orders_today = db.query(Order).filter(
        func.date(Order.created_at) == today
    ).count()

    # Pending Payment
    pending_payment = db.query(OrderPayment).filter(
        OrderPayment.payment_status == "Unchecked"
    ).count()

    # Checked Orders
    checked_orders = db.query(Order).filter(
        Order.order_status == "Checked"
    ).count()

    # Packing Orders
    packing_orders = db.query(Order).filter(
        Order.order_status == "Packing"
    ).count()

    # Revenue Today
    items_today = (
        db.query(OrderItem)
        .join(Order)
        .filter(func.date(Order.created_at) == today)
        .all()
    )

    revenue_today = 0
    for item in items_today:
        revenue_today += float(item.unit_price) - float(item.discount)

    return {
        "orders_today": orders_today,
        "pending_payment": pending_payment,
        "checked_orders": checked_orders,
        "packing_orders": packing_orders,
        "revenue_today": revenue_today
    }

@router.get("/today/print")
def get_today_shipping_orders(
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    today = date.today()

    orders = (
        db.query(Order)
        .filter(Order.shipping_date == today)
        .order_by(Order.created_at.asc())
        .all()
    )

    result = []

    for order in orders:
        items = (
            db.query(OrderItem)
            .filter(OrderItem.order_id == order.id)
            .all()
        )

        result.append({
            "order": order,
            "items": items
        })

    return result


@router.get("/today-pack")
def get_today_pack_orders(
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    ดึงเฉพาะออเดอร์ที่:
    - order_status = Checked
    - shipping_date = วันนี้
    """

    today = date.today()

    orders = (
        db.query(Order)
        .filter(
            Order.order_status == "Checked",
            Order.shipping_date == today
        )
        .order_by(Order.created_at.asc())
        .all()
    )

    return orders


@router.get("/today-pack/export")
def export_today_pack_orders(
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    today = date.today()

    orders = (
        db.query(Order)
        .filter(
            Order.order_status == "Checked",
            Order.shipping_date == today
        )
        .order_by(Order.created_at.asc())
        .all()
    )

    # สร้าง Excel
    wb = Workbook()
    ws = wb.active
    ws.title = "Today Pack"

    # Header
    ws.append([
        "Order Code",
        "Customer",
        "Phone",
        "Shipping Address",
        "Shipping Date"
    ])

    # Data
    for o in orders:
        ws.append([
            o.order_code,
            o.customer_name,
            o.customer_phone,
            o.shipping_address_text,
            str(o.shipping_date)
        ])

    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)

    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=today_pack_{today}.xlsx"
        },
    )


@router.post("/export-orders")
def export_orders_excel(
    created_from: str | None = Query(None, description="YYYY-MM-DD"),
    created_to: str | None = Query(None, description="YYYY-MM-DD"),
    sale_id: int | None = Query(None, description="Filter by sale_id (optional)"),
    payment_method: str | None = Query(None, description="cod | transfer | card_2c2p | card_pay"),
    payment_status: str | None = Query(None, description="Payment status filter (optional)"),
    order_status: str | None = Query(None, description="Order status filter (optional)"),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Export orders to an Excel file for accountant / manager.

    Filters:
    - created_from / created_to: order created_at date range
    - sale_id: specific sale (optional)
    - payment_method: payment method code (optional)
    """
    require_role(user, ["account", "manager"])

    query = (
        db.query(Order, OrderPayment, User)
        .join(OrderPayment, OrderPayment.order_id == Order.id)
        .outerjoin(User, User.id == Order.sale_id)
    )

    if created_from:
        try:
            dt_from = datetime.strptime(created_from, "%Y-%m-%d").date()
            query = query.filter(func.date(Order.created_at) >= dt_from)
        except ValueError:
            pass

    if created_to:
        try:
            dt_to = datetime.strptime(created_to, "%Y-%m-%d").date()
            query = query.filter(func.date(Order.created_at) <= dt_to)
        except ValueError:
            pass

    if sale_id is not None:
        query = query.filter(Order.sale_id == sale_id)

    if payment_method:
        query = query.filter(OrderPayment.payment_method == payment_method)

    if payment_status:
        query = query.filter(OrderPayment.payment_status == payment_status)

    if order_status:
        query = query.filter(Order.order_status == order_status)

    rows = query.order_by(Order.created_at.asc()).all()

    wb = Workbook()
    ws = wb.active
    ws.title = "Orders"

    # Columns (one row per order):
    # - Order Created Date
    # - Order ID (order_code)
    # - Sale
    # - Customer Name
    # - Payment Method
    # - Payment Status
    # - Order Status
    # - Net Price
    ws.append(
        [
            "Order Created Date",
            "Order ID",
            "Sale",
            "Customer Name",
            "Payment Method",
            "Payment Status",
            "Order Status",
            "Net Price",
        ]
    )

    for o, pay, sale_user in rows:
        net_total = _order_net_total(db, o.id)
        ws.append(
            [
                o.created_at.date().isoformat()
                if getattr(o, "created_at", None)
                else "",
                o.order_code or "",
                (sale_user.name if sale_user is not None else "") or "",
                o.customer_name or "",
                pay.payment_method or "",
                pay.payment_status or "",
                o.order_status or "",
                net_total,
            ]
        )

    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)

    filename_parts = ["orders"]
    if created_from:
        filename_parts.append(created_from)
    if created_to:
        filename_parts.append(created_to)
    filename = "_".join(filename_parts) + ".xlsx"

    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        },
    )


@router.post("/{order_id}/freebies")
def add_order_freebie(
    order_id: int,
    freebie_id: int,
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):

    new_freebie = OrderFreebie(
        order_id=order_id,
        freebie_id=freebie_id
    )

    db.add(new_freebie)
    db.commit()

    return {"message": "Freebie added to order"}


