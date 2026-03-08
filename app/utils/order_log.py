from app.models.order_log import OrderLog

def log_order_change(
    db,
    order_id: int,
    action: str,
    old_value,
    new_value,
    user_id: int
):
    log = OrderLog(
        order_id=order_id,
        action=action,
        old_value=str(old_value),
        new_value=str(new_value),
        performed_by=user_id
    )
    db.add(log)
