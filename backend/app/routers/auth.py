from __future__ import annotations

import secrets
from typing import Annotated
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, RedirectResponse

from app.database import one
from app.dependencies import get_current_user
from app.schemas import LoginRequest, LoginResponse, PasswordChangeRequest, UserResponse
from app.security import create_token, hash_password, verify_password


router = APIRouter(prefix="/api", tags=["auth"])
SESSION_COOKIE = "jetbao_session"
SSO_STATE_COOKIE = "jetbao_sso_state"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 12
SSO_STATE_MAX_AGE_SECONDS = 60 * 5


class SsoExchangeError(Exception):
    pass


class SsoClient:
    def __init__(
        self,
        token_url: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
    ):
        self.token_url = token_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

    def exchange_code(self, code: str) -> dict[str, str]:
        try:
            response = httpx.post(
                self.token_url,
                json={
                    "grant_type": "authorization_code",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "redirect_uri": self.redirect_uri,
                    "code": code,
                },
                timeout=10,
            )
            response.raise_for_status()
            payload = response.json()
            subject = payload.get("sub")
            email = payload.get("email")
            if not isinstance(subject, str) or not subject or not isinstance(email, str) or not email:
                raise SsoExchangeError("身份中心返回了无效身份")
            return {"sub": subject, "email": email.strip().lower()}
        except (httpx.HTTPError, ValueError, SsoExchangeError) as exc:
            raise SsoExchangeError("无法完成统一身份验证") from exc


def _set_session_cookie(response: JSONResponse | RedirectResponse, token: str, request: Request) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=request.app.state.settings.sso_cookie_secure,
        samesite="lax",
        path="/",
    )


def _clear_session_cookie(response: JSONResponse | RedirectResponse, request: Request) -> None:
    response.delete_cookie(
        SESSION_COOKIE,
        httponly=True,
        secure=request.app.state.settings.sso_cookie_secure,
        samesite="lax",
        path="/",
    )


def serialize_user(row) -> UserResponse:
    return UserResponse(
        id=row["id"],
        username=row["username"],
        email=row["email"] if "email" in row.keys() else None,
        role=row["role"],
        employee_name=row["employee_name"],
        company_entity=row["company_entity"],
        is_active=bool(row["is_active"]),
        guide_seen=bool(row["guide_seen"]) if "guide_seen" in row.keys() else False,
    )


@router.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest, request: Request) -> LoginResponse:
    if request.app.state.settings.auth_mode == "sso":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="请使用企业邮箱统一登录")
    with request.app.state.db.connect() as connection:
        user = one(connection, "SELECT * FROM users WHERE username = ?", (payload.username,))
    if user is None or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号或密码错误")
    if not bool(user["is_active"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已停用")
    token = create_token(user["id"], request.app.state.settings.secret_key)
    return LoginResponse(token=token, user=serialize_user(user))


@router.get("/auth/config")
def auth_config(request: Request) -> dict[str, str | bool]:
    mode = request.app.state.settings.auth_mode
    return {
        "mode": mode,
        "sso_enabled": mode in {"hybrid", "sso"},
        "legacy_enabled": mode in {"legacy", "hybrid"},
    }


@router.get("/auth/sso/start")
def start_sso(request: Request) -> RedirectResponse:
    settings = request.app.state.settings
    if settings.auth_mode not in {"hybrid", "sso"}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="统一登录未启用")
    state = secrets.token_urlsafe(32)
    authorize_url = f"{settings.sso_authorize_url}?{urlencode({
        'client_id': settings.sso_client_id,
        'redirect_uri': settings.sso_redirect_uri,
        'state': state,
    })}"
    response = RedirectResponse(authorize_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    response.set_cookie(
        SSO_STATE_COOKIE,
        state,
        max_age=SSO_STATE_MAX_AGE_SECONDS,
        httponly=True,
        secure=settings.sso_cookie_secure,
        samesite="lax",
        path="/api/auth/sso/callback",
    )
    return response


@router.get("/auth/sso/callback")
def finish_sso(
    request: Request,
    code: Annotated[str, Query(min_length=1)],
    state_value: Annotated[str, Query(alias="state", min_length=1)],
    expected_state: Annotated[str | None, Cookie(alias=SSO_STATE_COOKIE)] = None,
) -> RedirectResponse:
    if not expected_state or not secrets.compare_digest(expected_state, state_value):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="统一登录状态无效，请重新登录")
    try:
        identity = request.app.state.sso_client.exchange_code(code)
    except SsoExchangeError:
        return RedirectResponse("/?sso_error=identity_exchange_failed", status_code=status.HTTP_303_SEE_OTHER)

    with request.app.state.db.connect() as connection:
        user = one(
            connection,
            "SELECT * FROM users WHERE lower(email) = ?",
            (identity["email"].lower(),),
        )
        if user is None or not bool(user["is_active"]):
            response = RedirectResponse("/?sso_error=access_not_provisioned", status_code=status.HTTP_303_SEE_OTHER)
            response.delete_cookie(SSO_STATE_COOKIE, path="/api/auth/sso/callback")
            return response
        if user["identity_id"] and user["identity_id"] != identity["sub"]:
            response = RedirectResponse("/?sso_error=identity_mismatch", status_code=status.HTTP_303_SEE_OTHER)
            response.delete_cookie(SSO_STATE_COOKIE, path="/api/auth/sso/callback")
            return response
        if not user["identity_id"]:
            connection.execute(
                "UPDATE users SET identity_id = ? WHERE id = ?",
                (identity["sub"], user["id"]),
            )

    response = RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    _set_session_cookie(response, create_token(user["id"], request.app.state.settings.secret_key), request)
    response.delete_cookie(SSO_STATE_COOKIE, path="/api/auth/sso/callback")
    return response


@router.post("/auth/logout")
def logout(request: Request) -> JSONResponse:
    settings = request.app.state.settings
    if settings.auth_mode == "legacy":
        logout_url = "/"
    else:
        redirect_uri = settings.sso_redirect_uri.rsplit("/api/", 1)[0] + "/"
        logout_url = f"{settings.sso_logout_url}?{urlencode({'redirect': redirect_uri})}"
    response = JSONResponse({"logout_url": logout_url})
    _clear_session_cookie(response, request)
    return response


@router.get("/me", response_model=UserResponse)
def me(user=Depends(get_current_user)) -> UserResponse:
    return serialize_user(user)


@router.post("/me/guide-seen", response_model=UserResponse)
def mark_guide_seen(request: Request, user=Depends(get_current_user)) -> UserResponse:
    with request.app.state.db.connect() as connection:
        connection.execute("UPDATE users SET guide_seen = 1 WHERE id = ?", (user["id"],))
        updated = one(connection, "SELECT * FROM users WHERE id = ?", (user["id"],))
    return serialize_user(updated)


@router.patch("/me/password", response_model=UserResponse)
def change_password(
    payload: PasswordChangeRequest,
    request: Request,
    user=Depends(get_current_user),
) -> UserResponse:
    if request.app.state.settings.auth_mode == "sso":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="企业邮箱账号无需在 JetBao 修改密码")
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
