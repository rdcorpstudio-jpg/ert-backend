from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import SessionLocal
from app.models.user import User
from app.core.security import verify_password, create_token, hash_password
from app.deps import get_current_user
from app.core.permissions import require_role

router = APIRouter(prefix="/auth")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class CreateUserBody(BaseModel):
    email: str
    password: str
    name: str
    role: str  # sale, account, pack, manager


@router.post("/register")
def register_user(
    body: CreateUserBody,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user, ["manager"])
    existing = db.query(User).filter(User.email == body.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    if body.role not in ("sale", "account", "pack", "manager"):
        raise HTTPException(status_code=400, detail="Invalid role")
    u = User(
        email=body.email,
        password_hash=hash_password(body.password),
        name=body.name or body.email,
        role=body.role,
    )
    db.add(u)
    db.commit()
    return {"message": "User created", "id": u.id}


@router.post("/login")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.email == form_data.username).first()

    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_token({
        "user_id": user.id,
        "role": user.role
    })

    return {
        "access_token": token,
        "token_type": "bearer"
    }
