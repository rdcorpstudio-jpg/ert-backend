from sqlalchemy import Column, Integer, String, DateTime, Text, Date, Numeric
from sqlalchemy.sql import func
from app.database import Base

class OrderPayment(Base):
    __tablename__ = "order_payments"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, unique=True)

    payment_method = Column(String(50))  
    deposit_amount = Column(Numeric(12, 2), nullable=True)
    payment_status = Column(String(20), default="Unchecked")

    checked_by = Column(Integer, nullable=True)
    checked_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=func.now())

    installment_type = Column(String(50), nullable=True)  # full / installment
    installment_months = Column(Integer, nullable=True)  # 6 / 10
    paid_date = Column(DateTime, nullable=True)
    paid_note = Column(Text, nullable=True)
