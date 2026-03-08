from sqlalchemy import Column, Integer, ForeignKey, String
from app.database import Base

class OrderItemFreebie(Base):
    __tablename__ = "order_item_freebies"

    id = Column(Integer, primary_key=True)

    order_item_id = Column(Integer, ForeignKey("order_items.id"))
    freebie_id = Column(Integer, ForeignKey("freebies.id"))
