from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.database import one
from app.dependencies import get_current_user
from app.schemas import LoginRequest, LoginResponse, UserResponse
from app.security import create_token, verify_password


router = APIRouter(prefix="/api", tags=["auth"])


def serialize_user(row) -> UserResponse:
    return UserResponse(
        id=row["id"],
        username=row["username"],
        role=row["role"],
        employee_name=row["employee_name"],
        company_entity=row["company_entity"],
        is_active=bool(row["is_active"]),
    )


@router.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest, request: Request) -> LoginResponse:
    with request.app.state.db.connect() as connection:
        user = one(connection, "SELECT * FROM users WHERE username = ?", (payload.username,))
    if user is None or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号或密码错误")
    if not bool(user["is_active"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已停用")
    token = create_token(user["id"], request.app.state.settings.secret_key)
    return LoginResponse(token=token, user=serialize_user(user))


@router.get("/me", response_model=UserResponse)
def me(user=Depends(get_current_user)) -> UserResponse:
    return serialize_user(user)
