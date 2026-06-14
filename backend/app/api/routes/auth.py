from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.services.auth import LoginRequest, TokenResponse, authenticate_user, create_jwt_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest) -> TokenResponse:
    user = authenticate_user(payload.username, payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "INVALID_CREDENTIALS", "message": "用户名或密码错误。", "details": {}}},
        )
    token = create_jwt_token(user["username"], user["role"])
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        username=user["username"],
        role=user["role"],
    )
