import json
import logging
import os
from typing import Optional
from urllib import request, error

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.models.order import Order
from app.models.user import User
from app.models.order_item import OrderItem
from app.models.order_payment import OrderPayment
from app.models.order_freebie import OrderFreebie
from app.models.freebie import Freebie
from app.models.order_item_freebie import OrderItemFreebie
from app.models.line_notification_config import LineNotificationConfig


def _channel_access_token_from_env() -> str:
    return (os.getenv("LINE_CHANNEL_ACCESS_TOKEN") or "").strip()


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
        "deposit_cod": "มัดจำ + เก็บเงินปลายทาง",
        "deposit_transfer": "มัดจำ + โอน",
        "deposit_card_2c2p": "มัดจำ + บัตรเครดิต (2C2P)",
        "deposit_card_pay": "มัดจำ + บัตรเครดิต (Pay)",
        "transfer": "โอน",
        "card_2c2p": "บัตรเครดิต (2C2P)",
        "card_pay": "บัตรเครดิต (Pay)",
    }
    payment_method_text = payment_method_map.get(payment_method_raw, payment_method_raw or "-")

    # Discount: show same as sale submit — percentage when it matches a clean % of price,
    # otherwise show flat "X บาท" (with special handling for 1000).
    def _discount_label(unit_price: float, discount: float) -> str:
        if discount <= 0:
            return ""
        # Flat 1000 baht option from dropdown
        if abs(discount - 1000) < 0.01:
            return "1,000 บาท"
        if unit_price and unit_price > 0:
            pct = (discount / unit_price) * 100.0
            nearest = round(pct)
            # If percentage is very close to a whole number (e.g. 5, 8, 10, 25, 26, 28, ...)
            if 1 <= nearest <= 99 and abs(pct - nearest) < 0.25:
                return f"{nearest}%"
        return f"{discount:,.2f} บาท"

    discount_parts = [
        _discount_label(float(i.unit_price or 0), float(i.discount or 0))
        for i in items
    ]
    discount_parts = [s for s in discount_parts if s]
    discount_text = ", ".join(discount_parts) if discount_parts else "-"

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

    page_name_raw = (getattr(order, "pageName", None) or "").strip()
    page_name_text = page_name_raw if page_name_raw else "-"

    net_total = _order_net_total(db, order.id)
    net_text = f"{net_total:,.2f} บาท"

    if payment_method_raw in {"deposit_cod", "deposit_transfer", "deposit_card_2c2p", "deposit_card_pay"} and payment and payment.deposit_amount is not None:
        dep = float(payment.deposit_amount)
        remain = max(0.0, float(net_total) - dep)
        if payment_method_raw == "deposit_cod":
            remain_label = "ปลายทาง"
        elif payment_method_raw == "deposit_transfer":
            remain_label = "โอน"
        else:
            remain_label = "บัตร"
        payment_method_text = f"{payment_method_text} (มัดจำ {dep:,.2f} บาท / {remain_label} {remain:,.2f} บาท)"

    shipping_note = (order.shipping_note or "").strip() or "-"

    sale_name = sale.name if sale and sale.name else "-"

    text = (
        "💃เย้ๆ มีลูกค้าสั่งอีกแล้วว🎉\n\n"
        f"🚀ขายเก่งสุดๆ : {sale_name}\n"
        f"😚 ลูกค้าซื้อ: {product_text}\n"
        f"🔖จ่าย : {payment_method_text}\n"
        f"🔖ส่วนลด : {discount_text}\n"
        f"🔖 แถม : {freebie_text} \n"
        f"จากเพจ: {page_name_text}\n\n"
        f"👍ยอดรวม: {net_text}\n"
        f"หมายเหตุ: {shipping_note}\n"
    )
    return text


def send_order_created_notification(db: Session, order_id: int) -> None:
    """Push LINE message when a new Pending order is created. Logs errors; does not raise."""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        logger.warning("LINE order-created notify: order id=%s not found", order_id)
        return

    # Find first active line config row; later we can filter by category.
    config = (
        db.query(LineNotificationConfig)
        .filter(LineNotificationConfig.is_active == True)
        .order_by(LineNotificationConfig.id.asc())
        .first()
    )
    if not config:
        logger.warning(
            "LINE order-created notify: no active row in line_notification_config "
            "(need is_active=true and group_id)"
        )
        return
    if not (config.group_id or "").strip():
        logger.warning(
            "LINE order-created notify: line_notification_config id=%s has empty group_id",
            config.id,
        )
        return

    # Channel access token: env is primary; DB line_token is fallback (same as /line-config UI).
    line_token = _channel_access_token_from_env() or (config.line_token or "").strip()
    if not line_token:
        logger.warning(
            "LINE order-created notify: missing token. Set env LINE_CHANNEL_ACCESS_TOKEN "
            "or line_token on an active line_notification_config row."
        )
        return

    try:
        text = _build_order_created_message(db, order)
    except Exception:
        logger.exception("LINE order-created notify: failed to build message for order id=%s", order_id)
        return

    if not text:
        logger.warning("LINE order-created notify: empty message for order id=%s", order_id)
        return

    body = {
        "to": config.group_id.strip(),
        "messages": [
          {"type": "text", "text": text}
        ],
    }
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")

    req = request.Request(
        "https://api.line.me/v2/bot/message/push",
        data=data,
        method="POST",
    )
    req.add_header("Content-Type", "application/json; charset=UTF-8")
    req.add_header("Authorization", f"Bearer {line_token}")

    try:
        with request.urlopen(req, timeout=15) as resp:
            resp.read()
    except error.HTTPError as e:
        try:
            err_body = e.read().decode("utf-8", errors="replace")
        except Exception:
            err_body = str(e)
        logger.warning(
            "LINE order-created notify: HTTP %s from LINE API: %s",
            getattr(e, "code", "?"),
            err_body[:500],
        )
    except error.URLError as e:
        logger.warning("LINE order-created notify: network error: %s", e)

