def sync_order_status_with_payment(order, payment_status: str, shipping_method: str | None = None):
    """
    ปรับ order_status ตาม payment_status.
    When payment_status is Checked and shipping_method is Special → order_status "Special".
    """

    if payment_status == "Unchecked":
        order.order_status = "Pending"

    elif payment_status == "Checked":
        if (shipping_method or "").strip().lower() == "special":
            order.order_status = "Special"
        else:
            order.order_status = "Checked"

    # Paid / Received / Unmatched
    # ❗ ไม่ยุ่ง order_status
