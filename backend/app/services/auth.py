from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from app.config import settings

security = HTTPBearer(auto_error=False)


def _hash_password(password: str, salt: str = "") -> tuple[str, str]:
    if not salt:
        salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000)
    return salt + ":" + dk.hex(), salt


def _verify_password(plain: str, stored: str) -> bool:
    salt = stored.split(":", 1)[0]
    hashed, _ = _hash_password(plain, salt)
    return secrets.compare_digest(hashed, stored)


_ADMIN_HASH, _ = _hash_password("admin123")
_USER_HASH, _ = _hash_password("user123")

PRESET_USERS: dict[str, dict[str, Any]] = {
    "admin": {
        "username": "admin",
        "hashed_password": _ADMIN_HASH,
        "role": "admin",
    },
    "user": {
        "username": "user",
        "hashed_password": _USER_HASH,
        "role": "user",
    },
}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    username: str
    role: str


class LoginRequest(BaseModel):
    username: str
    password: str


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_jwt_token(username: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {
        "sub": username,
        "role": role,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_jwt_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None


def authenticate_user(username: str, password: str) -> dict[str, Any] | None:
    user = PRESET_USERS.get(username)
    if not user:
        return None
    if not _verify_password(password, user["hashed_password"]):
        return None
    return user


def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "UNAUTHORIZED", "message": "请先登录。", "details": {}}},
        )
    payload = decode_jwt_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "UNAUTHORIZED", "message": "Token 无效或已过期。", "details": {}}},
        )
    username = payload.get("sub", "")
    user = PRESET_USERS.get(username)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "UNAUTHORIZED", "message": "用户不存在。", "details": {}}},
        )
    return user
