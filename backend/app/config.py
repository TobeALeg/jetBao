from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from app.company_entities import is_allowed_company_entity, normalize_company_entity


def _load_env_file(project_dir: Path) -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(project_dir / ".env")


def _resolve_env_path(value: str | None, default: Path, base_dir: Path) -> Path:
    if not value:
        return default.resolve()
    path = Path(value)
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class BootstrapAdmin:
    username: str
    password: str
    employee_name: str
    company_entity: str


@dataclass(frozen=True)
class Settings:
    secret_key: str
    auth_mode: str
    sso_authorize_url: str
    sso_token_url: str
    sso_client_id: str
    sso_client_secret: str
    sso_redirect_uri: str
    sso_email_domain: str
    sso_cookie_secure: bool
    sso_logout_url: str
    data_dir: Path
    upload_dir: Path
    database_path: Path
    tencent_secret_id: str
    tencent_secret_key: str
    tencent_ocr_region: str
    tencent_ocr_endpoint: str
    tencent_ocr_action: str
    tencent_ocr_pdf_page: int
    tencent_ocr_enable_multiple_page: bool
    seed_demo_users: bool
    bootstrap_admin: BootstrapAdmin | None

    @classmethod
    def from_env(cls) -> "Settings":
        backend_dir = Path(__file__).resolve().parents[1]
        project_dir = backend_dir.parent
        _load_env_file(project_dir)
        data_dir = _resolve_env_path(os.getenv("DATA_DIR"), backend_dir / "data", project_dir)
        upload_dir = _resolve_env_path(os.getenv("UPLOAD_DIR"), data_dir / "uploads", project_dir)
        bootstrap_admin = _bootstrap_admin_from_env()
        auth_mode = os.getenv("AUTH_MODE", "legacy").strip().lower()
        if auth_mode not in {"legacy", "hybrid", "sso"}:
            raise ValueError("AUTH_MODE 必须是 legacy、hybrid 或 sso")
        sso_settings = {
            "sso_authorize_url": os.getenv("SSO_AUTHORIZE_URL", "").strip(),
            "sso_token_url": os.getenv("SSO_TOKEN_URL", "").strip(),
            "sso_client_id": os.getenv("SSO_CLIENT_ID", "").strip(),
            "sso_client_secret": os.getenv("SSO_CLIENT_SECRET", ""),
            "sso_redirect_uri": os.getenv("SSO_REDIRECT_URI", "").strip(),
        }
        if auth_mode in {"hybrid", "sso"} and not all(sso_settings.values()):
            raise ValueError("启用统一登录时必须完整配置 SSO_AUTHORIZE_URL、SSO_TOKEN_URL、SSO_CLIENT_ID、SSO_CLIENT_SECRET 和 SSO_REDIRECT_URI")
        return cls(
            secret_key=os.getenv("SECRET_KEY", "dev-secret-change-me"),
            auth_mode=auth_mode,
            **sso_settings,
            sso_cookie_secure=_env_bool("SSO_COOKIE_SECURE", True),
            sso_logout_url=os.getenv("SSO_LOGOUT_URL", "https://mentti.work/api/auth/logout").strip(),
            sso_email_domain=os.getenv("SSO_EMAIL_DOMAIN", "mentitrek.com").strip().lower(),
            data_dir=data_dir,
            upload_dir=upload_dir,
            database_path=data_dir / "jetbao.sqlite3",
            tencent_secret_id=os.getenv("TENCENT_SECRET_ID", ""),
            tencent_secret_key=os.getenv("TENCENT_SECRET_KEY", ""),
            tencent_ocr_region=os.getenv("TENCENT_OCR_REGION", "ap-guangzhou"),
            tencent_ocr_endpoint=os.getenv("TENCENT_OCR_ENDPOINT", "ocr.tencentcloudapi.com"),
            tencent_ocr_action=os.getenv("TENCENT_OCR_ACTION", "RecognizeGeneralInvoice"),
            tencent_ocr_pdf_page=_env_int("TENCENT_OCR_PDF_PAGE", 1),
            tencent_ocr_enable_multiple_page=os.getenv("TENCENT_OCR_ENABLE_MULTIPLE_PAGE", "true").lower() == "true",
            seed_demo_users=os.getenv("SEED_DEMO_USERS", "false").lower() == "true",
            bootstrap_admin=bootstrap_admin,
        )


def _bootstrap_admin_from_env() -> BootstrapAdmin | None:
    username = os.getenv("BOOTSTRAP_ADMIN_USERNAME", "").strip()
    password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "")
    if not username and not password:
        return None
    if not username or not password:
        raise ValueError("BOOTSTRAP_ADMIN_USERNAME 和 BOOTSTRAP_ADMIN_PASSWORD 必须同时设置")
    company_entity = normalize_company_entity(os.getenv("BOOTSTRAP_ADMIN_COMPANY_ENTITY", ""))
    if not is_allowed_company_entity(company_entity):
        raise ValueError("BOOTSTRAP_ADMIN_COMPANY_ENTITY 必须是系统允许的公司主体")
    return BootstrapAdmin(
        username=username,
        password=password,
        employee_name=os.getenv("BOOTSTRAP_ADMIN_EMPLOYEE_NAME", username).strip() or username,
        company_entity=company_entity,
    )
