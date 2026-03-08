# app/schemas/login.py
from pydantic import BaseModel

class LoginRequest(BaseModel):
    email: str
    password: str
