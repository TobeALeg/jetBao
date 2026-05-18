from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status

from app.database import one
from app.security import parse_token


def get_database(request: Request):
    return request.app.state.db


def get_settings(request: Request):
    return request.app.state.settings


def get_current_user(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> sqlite3.Row:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    token = authorization.removeprefix("Bearer ").strip()
    payload = parse_token(token, request.app.state.settings.secret_key)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已失效")
    with request.app.state.db.connect() as connection:
        user = one(connection, "SELECT * FROM users WHERE id = ?", (payload.user_id,))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号不存在")
    if not bool(user["is_active"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已停用")
    return user


def require_admin(user: sqlite3.Row = Depends(get_current_user)) -> sqlite3.Row:
    if user["role"] != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return user
