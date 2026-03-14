# กำหนดว่า status ไหน → ไป status ไหนได้ (manual change)
# Pending → Checked ไม่ได้: ให้ sync จาก payment status (account เปลี่ยนเป็น Checked) เท่านั้น หลังจาก Checked แล้วค่อยเปลี่ยน Packing ฯลฯ ได้
# Special: own-fleet orders; packing team cannot move. No next status.
ORDER_STATUS_FLOW = {
    "Pending": [],  # Checked มาจาก sync การชำระเงินเท่านั้น
    "Checked": ["Packing"],
    "Packing": ["Shipped", "Fail"],
    "Shipped": ["Success", "Fail"],
    "Fail": ["Return Received"],
    "Return Received": [],
    "Success": [],
    "Special": [],  # Packing cannot change; account can still manage payment status
}

def can_change_order_status(current_status: str, new_status: str) -> bool:
    allowed_next = ORDER_STATUS_FLOW.get(current_status, [])
    return new_status in allowed_next
