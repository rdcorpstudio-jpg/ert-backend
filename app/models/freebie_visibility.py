from sqlalchemy import Boolean, Column, ForeignKey, Integer
from app.database import Base


class FreebieVisibility(Base):
    __tablename__ = "freebie_visibility"

    freebie_id = Column(Integer, ForeignKey("freebies.id"), primary_key=True)
    is_active = Column(Boolean, default=True, nullable=False)
