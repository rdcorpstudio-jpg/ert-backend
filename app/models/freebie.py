from sqlalchemy import Column, Integer, String
from app.database import Base

class Freebie(Base):
    __tablename__ = "freebies"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True)
