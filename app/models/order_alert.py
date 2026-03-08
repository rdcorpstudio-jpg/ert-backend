from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func
from app.database import Base

class OrderAlert(Base):
    __tablename__ = "order_alerts"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer)

    alert_type = Column(String(50))
    message = Column(String(255))

    target_role = Column(String(20))  # pack / account
    is_read = Column(Boolean, default=False)

    created_at = Column(DateTime, default=func.now())
