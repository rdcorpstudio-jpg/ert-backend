from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import SessionLocal
from app.deps import get_current_user
from app.core.permissions import require_role
from app.models.line_notification_config import LineNotificationConfig
from pydantic import BaseModel


router = APIRouter(prefix="/line-config")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class LineNotificationConfigItem(BaseModel):
    id: Optional[int] = None
    category: Optional[str] = None
    line_token: Optional[str] = None
    group_id: Optional[str] = None
    note: Optional[str] = None
    is_active: bool = True

    class Config:
        orm_mode = True


class LineNotificationConfigPayload(BaseModel):
    items: List[LineNotificationConfigItem]


@router.get("")
def get_line_config(
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return all line notification config rows (manager only)."""
    require_role(user, ["manager"])
    rows = (
        db.query(LineNotificationConfig)
        .order_by(LineNotificationConfig.id.asc())
        .all()
    )
    items: List[LineNotificationConfigItem] = [
        LineNotificationConfigItem.from_orm(r) for r in rows
    ]
    return {"items": items}


@router.put("")
def save_line_config(
    payload: LineNotificationConfigPayload,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Replace all line notification config rows with the given list (manager only)."""
    require_role(user, ["manager"])
    # Clear existing
    db.query(LineNotificationConfig).delete()
    db.flush()

    for item in payload.items:
        # Skip completely empty rows
        if not (item.category or item.line_token or item.group_id or item.note):
            continue
        row = LineNotificationConfig(
            category=item.category or None,
            line_token=item.line_token or None,
            group_id=item.group_id or None,
            note=item.note or None,
            is_active=item.is_active,
        )
        db.add(row)

    db.commit()
    return {"message": "saved"}

