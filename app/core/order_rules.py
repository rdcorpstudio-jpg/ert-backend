def can_edit_shipping_address(role: str, order_status: str) -> bool:
    if role == "manager":
        return True

    if role == "sale":
        return order_status in ["Pending", "Checked"]

    return False


def can_edit_product(
    role: str,
    order_status: str,
    net_total: float | None = None,
    net_total_at_check: float | None = None,
) -> bool:
    """Main product editable: Pending always; Checked/Packing only if net total unchanged; never after Shipped."""
    if order_status in ("Shipped", "Success", "Fail", "Return Received"):
        return False
    if role == "manager":
        if order_status in ("Checked", "Packing"):
            if net_total is not None and net_total_at_check is not None:
                return abs(float(net_total) - float(net_total_at_check)) < 0.01
        return True
    if role == "sale":
        if order_status == "Pending":
            return True
        if order_status in ("Checked", "Packing"):
            if net_total is not None and net_total_at_check is not None:
                return abs(float(net_total) - float(net_total_at_check)) < 0.01
            return False
    return False


def can_edit_freebie_note(role: str, order_status: str) -> bool:
    """Freebie note editable when order status is not Shipped or above (Pending, Checked, Packing)."""
    if role == "manager":
        return True
    return order_status not in ("Shipped", "Success", "Fail", "Return Received")


def can_edit_payment(role: str, payment_status: str) -> bool:
    if role == "manager":
        return True

    if role == "sale":
        return payment_status == "Unchecked"

    return False
