from datetime import date
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.order import Order

def generate_order_code(db: Session):
    # 1. เอาวันปัจจุบัน
    today = date.today()
    prefix = today.strftime("SG-%y-%m-%d")

    # 2. หาเลขรันสูงสุดของวันนี้ (ใช้ MAX แทน COUNT เพื่อลดโอกาสซ้ำเมื่อมี concurrent request)
    row = (
        db.query(func.max(Order.order_code))
        .filter(Order.order_code.like(f"{prefix}%"))
        .scalar()
    )
    if row is None:
        next_num = 1
    else:
        # row is like "SG-26-03-11-00011" -> take part after last "-"
        try:
            next_num = int(row.split("-")[-1]) + 1
        except (ValueError, IndexError):
            next_num = 1

    running = str(next_num).zfill(5)
    return f"{prefix}-{running}"
