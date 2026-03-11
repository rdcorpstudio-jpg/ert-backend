import json
import os
from typing import Optional
from urllib import request, error

from sqlalchemy.orm import Session

from app.models.order import Order
from app.models.user import User
from app.models.order_item import OrderItem
from app.models.order_payment import OrderPayment
from app.models.order_freebie import OrderFreebie
from app.models.freebie import Freebie
from app.models.order_item_freebie import OrderItemFreebie
from app.models.line_notification_config import LineNotificationConfig


LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")


def _order_net_total(db: Session, order_id: int) -> float:
    items = db.query(OrderItem).filter(OrderItem.order_id == order_id).all()
    return sum(float(i.unit_price) - float(i.discount or 0) for i in items)


def _build_order_created_message(db: Session, order: Order) -> Optional[str]:
    sale: Optional[User] = None
    if order.sale_id:
        sale = db.query(User).filter(User.id == order.sale_id).first()
    items = db.query(OrderItem).filter(OrderItem.order_id == order.id).all()
    product_names = [i.product_name for i in items if i.product_name]
    product_text = ", ".join(product_names) if product_names else "-"

    payment = db.query(OrderPayment).filter(OrderPayment.order_id == order.id).first()
    payment_method_raw = (payment.payment_method or "").strip() if payment else ""
    payment_method_map = {
        "cod": "เก็บเงินปลายทาง",
        "transfer": "โอน",
        "card_2c2p": "บัตรเครดิต (2C2P)",
        "card_pay": "บัตรเครดิต (Pay)",
    }
    payment_method_text = payment_method_map.get(payment_method_raw, payment_method_raw or "-")

    total_discount = sum(float(i.discount or 0) for i in items)
    discount_text = f"{total_discount:,.2f} บาท"

    # Freebie names: order-level first, fallback to item-level
    freebie_names = [
        r[0]
        for r in db.query(Freebie.name)
        .join(OrderFreebie, OrderFreebie.freebie_id == Freebie.id)
        .filter(OrderFreebie.order_id == order.id)
        .all()
    ]
    if not freebie_names:
        freebie_names = [
            r[0]
            for r in db.query(Freebie.name)
            .join(OrderItemFreebie, OrderItemFreebie.freebie_id == Freebie.id)
            .join(OrderItem, OrderItem.id == OrderItemFreebie.order_item_id)
            .filter(OrderItem.order_id == order.id)
            .all()
        ]
    freebie_text = ", ".join(freebie_names) if freebie_names else "-"

    net_total = _order_net_total(db, order.id)
    net_text = f"{net_total:,.2f} บาท"

    shipping_note = (order.shipping_note or "").strip() or "-"

    sale_name = sale.name if sale and sale.name else "-"

    text = (
        "💃เย้ๆ มีลูกค้าสั่งอีกแล้วว🎉\n\n"
        f"🚀ขายเก่งสุดๆ : {sale_name}\n"
        f"😚 ลูกค้าซื้อ: {product_text}\n"
        f"🔖จ่าย : {payment_method_text}\n"
        f"🔖ส่วนลด : {discount_text}\n"
        f"🔖 แถม : {freebie_text} \n\n"
        f"👍ยอดรวม: {net_text}\n"
        f"หมายเหตุ: {shipping_note}\n"
    )
    return text


def send_order_created_notification(db: Session, order_id: int) -> None:
    """Push LINE message when a new Pending order is created. Fails silently on error."""
    if not LINE_CHANNEL_ACCESS_TOKEN:
        return

    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        return

    # Find first active line config row; later we can filter by category.
    config = (
        db.query(LineNotificationConfig)
        .filter(LineNotificationConfig.is_active == True)
        .order_by(LineNotificationConfig.id.asc())
        .first()
    )
    if not config or not config.group_id:
        return

    text = _build_order_created_message(db, order)
    if not text:
        return

    body = {
        "to": config.group_id,
        "messages": [
          {"type": "text", "text": text}
        ],
    }
    data = json.dumps(body).encode("utf-8")

    req = request.Request(
        "https://api.line.me/v2/bot/message/push",
        data=data,
        method="POST",
    )
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}")

    try:
        with request.urlopen(req, timeout=5) as resp:
            # We don't care about body; just ensure request is sent.
            resp.read()
    except error.URLError:
        # Fail silently; do not break order creation.
        return

