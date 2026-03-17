from sqlalchemy import Column, Integer, String
from app.database import Base


class PageName(Base):
    __tablename__ = "page_names"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), unique=True, nullable=False)

