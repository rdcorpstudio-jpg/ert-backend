from sqlalchemy import Column, Integer, ForeignKey, Numeric, String
from app.database import Base

class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True)

    order_id = Column(Integer, ForeignKey("orders.id"))
    product_id = Column(Integer, ForeignKey("products.id"))

    product_name = Column(String(100))   # snapshot
    unit_price = Column(Numeric(10, 2))  # snapshot

    discount = Column(Numeric(10, 2), default=0)

from sqlalchemy.orm import relationship

freebies = relationship("OrderItemFreebie", backref="order_item")
