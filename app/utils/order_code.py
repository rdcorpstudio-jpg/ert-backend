from datetime import date
from sqlalchemy.orm import Session
from app.models.order import Order

def generate_order_code(db: Session):
    # 1. เอาวันปัจจุบัน
    today = date.today()

    # 2. สร้าง prefix เช่น SG-26-02-09
    prefix = today.strftime("SG-%y-%m-%d")

    # 3. นับจำนวน Order ของวันนี้
    count_today = (
        db.query(Order)
        .filter(Order.order_code.like(f"{prefix}%"))
        .count()
    )

    # 4. running number 00001
    running = str(count_today + 1).zfill(5)

    # 5. รวมเป็น Order Code เต็ม
    return f"{prefix}-{running}"
