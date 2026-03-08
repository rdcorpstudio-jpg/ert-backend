from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from app.database import Base

class OrderFile(Base):
    __tablename__ = "order_files"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer)
    file_type = Column(String(50))
    file_url = Column(String(255))
    uploaded_by = Column(Integer)
    uploaded_at = Column(DateTime, default=func.now())
