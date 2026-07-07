from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse

from app.dependencies import get_current_user
from app.schemas import AttachmentPoolRequest, AttachmentResponse
from app.services.ocr import OcrService, OcrServiceConfig


router = APIRouter(prefix="/api", tags=["attachments"])


def _attachment_response(row) -> AttachmentResponse:
    return AttachmentResponse(
        id=row["id"],
        original_filename=row["original_filename"],
        file_hash=row["file_hash"],
        file_size=row["file_size"],
        duplicate_count=row["duplicate_count"],
        is_duplicate=row["duplicate_count"] > 0,
        pool_status=row["pool_status"],
        ocr_status=row["ocr_status"],
        ocr_result=json.loads(row["ocr_result"] or "{}"),
        created_at=row["created_at"],
    )


def _delete_file(path_value: str) -> None:
    try:
        Path(path_value).unlink(missing_ok=True)
    except OSError:
        pass


def _save_and_recognize_attachment(request: Request, file: UploadFile, user) -> AttachmentResponse:
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="缺少文件名")

    upload_dir: Path = request.app.state.settings.upload_dir
    upload_dir.mkdir(parents=True, exist_ok=True)

    suffix = Path(file.filename).suffix.lower()
    stored_name = f"{uuid4().hex}{suffix}"
    stored_path = upload_dir / stored_name

    digest = hashlib.sha256()
    file_size = 0
    with stored_path.open("wb") as output:
        while chunk := file.file.read(1024 * 1024):
            file_size += len(chunk)
            digest.update(chunk)
            output.write(chunk)

    if file_size == 0:
        stored_path.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="附件不能为空")

    file_hash = digest.hexdigest()
    ocr_config = OcrServiceConfig.from_settings(request.app.state.settings)
    ocr_status, ocr_result = OcrService(ocr_config).recognize(stored_path)

    with request.app.state.db.connect() as connection:
        duplicate_count = connection.execute(
            "SELECT COUNT(*) AS count FROM attachments WHERE file_hash = ?",
            (file_hash,),
        ).fetchone()["count"]
        cursor = connection.execute(
            """
            INSERT INTO attachments (
                user_id, original_filename, stored_path, file_hash, file_size,
                duplicate_count, pool_status, ocr_status, ocr_result
            )
            VALUES (?, ?, ?, ?, ?, ?, 'staged', ?, ?)
            """,
            (
                user["id"],
                file.filename,
                str(stored_path),
                file_hash,
                file_size,
                duplicate_count,
                ocr_status,
                json.dumps(ocr_result, ensure_ascii=False),
            ),
        )
        row = connection.execute("SELECT * FROM attachments WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return _attachment_response(row)


@router.post("/attachments", response_model=AttachmentResponse)
def upload_attachment(
    request: Request,
    file: UploadFile = File(...),
    user=Depends(get_current_user),
) -> AttachmentResponse:
    return _save_and_recognize_attachment(request, file, user)


@router.post("/attachments/batch", response_model=list[AttachmentResponse])
def upload_attachments(
    request: Request,
    files: list[UploadFile] = File(...),
    user=Depends(get_current_user),
) -> list[AttachmentResponse]:
    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请至少上传一个附件")
    return [_save_and_recognize_attachment(request, file, user) for file in files]


@router.post("/attachments/pool", response_model=list[AttachmentResponse])
def add_attachments_to_invoice_pool(
    payload: AttachmentPoolRequest,
    request: Request,
    user=Depends(get_current_user),
) -> list[AttachmentResponse]:
    attachment_ids = list(dict.fromkeys(payload.attachment_ids))
    placeholders = ",".join("?" for _ in attachment_ids)
    with request.app.state.db.connect() as connection:
        rows = connection.execute(
            f"""
            SELECT *
            FROM attachments
            WHERE id IN ({placeholders}) AND user_id = ?
            """,
            (*attachment_ids, user["id"]),
        ).fetchall()
        if len(rows) != len(attachment_ids):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="附件不存在或无权使用")

        linked = connection.execute(
            f"""
            SELECT COUNT(*) AS count
            FROM attachments
            WHERE id IN ({placeholders})
              AND (expense_id IS NOT NULL OR EXISTS (
                  SELECT 1
                  FROM expense_attachments
                  WHERE expense_attachments.attachment_id = attachments.id
              ))
            """,
            tuple(attachment_ids),
        ).fetchone()
        if linked["count"] > 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="已挂到花费记录的附件不能加入发票池")

        allocated = connection.execute(
            f"""
            SELECT COUNT(*) AS count
            FROM expense_invoice_allocations
            WHERE attachment_id IN ({placeholders})
            """,
            tuple(attachment_ids),
        ).fetchone()
        if allocated["count"] > 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="已匹配到报销项目的发票不能加入发票池")

        connection.execute(
            f"""
            UPDATE attachments
            SET pool_status = 'pooled'
            WHERE id IN ({placeholders}) AND user_id = ?
            """,
            (*attachment_ids, user["id"]),
        )
        updated = connection.execute(
            f"""
            SELECT *
            FROM attachments
            WHERE id IN ({placeholders}) AND user_id = ?
            ORDER BY created_at DESC
            """,
            (*attachment_ids, user["id"]),
        ).fetchall()
    return [_attachment_response(row) for row in updated]


@router.get("/attachments/{attachment_id}/content")
def get_attachment_content(
    attachment_id: int,
    request: Request,
    user=Depends(get_current_user),
) -> FileResponse:
    with request.app.state.db.connect() as connection:
        row = connection.execute(
            "SELECT * FROM attachments WHERE id = ? AND user_id = ?",
            (attachment_id, user["id"]),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="附件不存在")

    path = Path(row["stored_path"])
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="附件文件不存在")
    return FileResponse(path, filename=row["original_filename"])


@router.delete("/attachments/{attachment_id}")
def delete_attachment(
    attachment_id: int,
    request: Request,
    user=Depends(get_current_user),
) -> dict[str, bool]:
    with request.app.state.db.connect() as connection:
        row = connection.execute(
            "SELECT * FROM attachments WHERE id = ? AND user_id = ?",
            (attachment_id, user["id"]),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="附件不存在")

        allocation = connection.execute(
            "SELECT id FROM expense_invoice_allocations WHERE attachment_id = ? LIMIT 1",
            (attachment_id,),
        ).fetchone()
        if allocation is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="已匹配到报销项目的发票不能直接删除")

        expense_link = connection.execute(
            """
            SELECT 1
            FROM expense_attachments
            WHERE attachment_id = ?
            LIMIT 1
            """,
            (attachment_id,),
        ).fetchone()
        if row["expense_id"] is not None or expense_link is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="已挂到花费记录的附件请先从花费记录中删除")

        try:
            connection.execute("DELETE FROM attachments WHERE id = ?", (attachment_id,))
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="附件仍被其他记录使用，不能删除")

    _delete_file(row["stored_path"])
    return {"deleted": True}
