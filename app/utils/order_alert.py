from app.models.order_alert import OrderAlert

def create_order_alert(
    db,
    order_id: int,
    alert_type: str,
    message: str,
    target_role: str
):
    alert = OrderAlert(
        order_id=order_id,
        alert_type=alert_type,
        message=message,
        target_role=target_role
    )
    db.add(alert)
