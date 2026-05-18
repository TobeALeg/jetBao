from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


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

    @classmethod
    def from_env(cls) -> "Settings":
        backend_dir = Path(__file__).resolve().parents[1]
        project_dir = backend_dir.parent
        _load_env_file(project_dir)
        data_dir = _resolve_env_path(os.getenv("DATA_DIR"), backend_dir / "data", project_dir)
        upload_dir = _resolve_env_path(os.getenv("UPLOAD_DIR"), data_dir / "uploads", project_dir)
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
            seed_demo_users=os.getenv("SEED_DEMO_USERS", "true").lower() == "true",
        )
