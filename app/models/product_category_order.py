from sqlalchemy import Column, Integer, String

from app.database import Base


class ProductCategoryOrder(Base):
    __tablename__ = "product_category_order"

    category = Column(String(50), primary_key=True)
    sort_order = Column(Integer, nullable=False, default=0)
