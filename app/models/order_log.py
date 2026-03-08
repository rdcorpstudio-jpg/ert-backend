from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from app.database import Base

class OrderLog(Base):
    __tablename__ = "order_logs"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer)

    action = Column(String(50))
    old_value = Column(String(255))
    new_value = Column(String(255))

    performed_by = Column(Integer)
    performed_at = Column(DateTime, default=func.now())
