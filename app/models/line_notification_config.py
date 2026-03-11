from sqlalchemy import Column, Integer, String, Boolean
from app.database import Base


class LineNotificationConfig(Base):
    __tablename__ = "line_notification_config"

    id = Column(Integer, primary_key=True, index=True)
    category = Column(String(100), nullable=True)  # ถ้าเว้นว่าง = ใช้กับทุก category
    line_token = Column(String(255), nullable=True)  # สำหรับ LINE Notify หรือบันทึก token ต่อ group (optional)
    group_id = Column(String(255), nullable=True)  # LINE group ID (ใช้กับ Messaging API)
    note = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)

