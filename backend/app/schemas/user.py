import datetime
from typing import Optional
from pydantic import BaseModel


class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "sales"


class UserUpdate(BaseModel):
    role: Optional[str] = None
    status: Optional[str] = None


class PasswordReset(BaseModel):
    new_password: str


class UserLogin(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    username: str
    role: str
    status: str
    created_at: datetime.datetime

    class Config:
        from_attributes = True
