from sqlalchemy import Column, Integer

from app.database import Base


class ProductDisplayOrder(Base):
    __tablename__ = "product_display_order"

    product_id = Column(Integer, primary_key=True)
    sort_order = Column(Integer, nullable=False, default=0)
