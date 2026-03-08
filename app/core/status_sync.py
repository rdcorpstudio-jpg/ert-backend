def sync_order_status_with_payment(order, payment_status: str):
    """
    ปรับ order_status ตาม payment_status
    """

    if payment_status == "Unchecked":
        order.order_status = "Pending"

    elif payment_status == "Checked":
        order.order_status = "Checked"

    # Paid / Received / Unmatched
    # ❗ ไม่ยุ่ง order_status
