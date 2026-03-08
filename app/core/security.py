from passlib.context import CryptContext
from jose import jwt
from datetime import datetime, timedelta

SECRET_KEY = "CHANGE_ME_SUPER_SECRET"
ALGORITHM = "HS256"

pwd_context = CryptContext(
    schemes=["sha256_crypt"],  # 🔥 เปลี่ยนจาก bcrypt
    deprecated="auto"
)

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)

def create_token(data: dict, expires_minutes: int = 60 * 24):
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(minutes=expires_minutes)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
