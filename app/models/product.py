from sqlalchemy import Column, Integer, String, Numeric, Boolean, DateTime
from sqlalchemy.sql import func
from app.database import Base

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True)
    category = Column(String(50))      # ตู้อบ / ผ้าห่ม / Redlight
    name = Column(String(100))
    price = Column(Numeric(10, 2))

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
