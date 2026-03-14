def sync_order_status_with_payment(order, payment_status: str, payment_method: str | None = None):
    """
    ปรับ order_status ตาม payment_status.
    When payment_method is "special" and payment_status becomes "Checked",
    set order_status to "Special" (own-fleet, not for packing team).
    """

    if payment_status == "Unchecked":
        order.order_status = "Pending"

    elif payment_status == "Checked":
        if (payment_method or "").strip().lower() == "special":
            order.order_status = "Special"
        else:
            order.order_status = "Checked"

    # Paid / Received / Unmatched
    # ❗ ไม่ยุ่ง order_status
