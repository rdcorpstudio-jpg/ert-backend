from sqlalchemy import Boolean, Column, Integer, Numeric, String

from app.database import Base


class DiscountRule(Base):
    __tablename__ = "discount_rules"

    id = Column(Integer, primary_key=True)
    value = Column(Numeric(10, 2), nullable=False)
    discount_type = Column(String(10), nullable=False)  # percent | baht
    is_active = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
