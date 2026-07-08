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


@dataclass(frozen=True)
class BootstrapAdmin:
    username: str
    password: str
    employee_name: str
    company_entity: str


@dataclass(frozen=True)
class Settings:
    secret_key: str
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
        return cls(
            secret_key=os.getenv("SECRET_KEY", "dev-secret-change-me"),
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
