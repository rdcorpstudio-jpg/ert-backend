from sqlalchemy import Column, Integer, ForeignKey
from app.database import Base

class OrderFreebie(Base):
    __tablename__ = "order_freebies"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"))
    freebie_id = Column(Integer, ForeignKey("freebies.id"))
