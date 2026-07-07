from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.database import one
from app.dependencies import get_current_user
from app.schemas import LoginRequest, LoginResponse, PasswordChangeRequest, UserResponse
from app.security import create_token, hash_password, verify_password


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


@router.patch("/me/password", response_model=UserResponse)
def change_password(
    payload: PasswordChangeRequest,
    request: Request,
    user=Depends(get_current_user),
) -> UserResponse:
    if not verify_password(payload.current_password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前密码不正确")
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="新密码不能和当前密码相同")

    with request.app.state.db.connect() as connection:
        connection.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (hash_password(payload.new_password), user["id"]),
        )
        updated = one(connection, "SELECT * FROM users WHERE id = ?", (user["id"],))
    return serialize_user(updated)
