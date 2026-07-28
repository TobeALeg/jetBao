from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status

from app.company_entities import invoice_buyer_match_status, normalize_company_title
from app.dependencies import get_current_user
from app.schemas import (
    AttachmentResponse,
    ExpenseAllocationBatchCreateRequest,
    ExpenseAllocationCreateRequest,
    ExpenseAllocationResponse,
    ExpenseAttachmentLinkRequest,
    ExpenseBatchCreateRequest,
    ExpenseCreateRequest,
    ExpenseResponse,
    ExpenseSubmitRequest,
    InvoicePoolItem,
    PendingExpenseSubmitRequest,
)


router = APIRouter(prefix="/api", tags=["expenses"])


def serialize_attachment(row) -> AttachmentResponse:
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


def serialize_allocation(row) -> ExpenseAllocationResponse:
    return ExpenseAllocationResponse(
        id=row["id"],
        expense_id=row["expense_id"],
        attachment_id=row["attachment_id"],
        invoice_item_index=row["invoice_item_index"],
        invoice_amount=row["invoice_amount"],
        allocated_amount=row["allocated_amount"],
        invoice_buyer=row["invoice_buyer"],
        invoice_number=row["invoice_number"],
        invoice_date=row["invoice_date"],
        invoice_type=row["invoice_type"],
        note=row["note"],
        created_at=row["created_at"],
    )


def _allocation_rows_for_expense(connection: sqlite3.Connection, expense_id: int) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT *
        FROM expense_invoice_allocations
        WHERE expense_id = ?
        ORDER BY created_at DESC, id DESC
        """,
        (expense_id,),
    ).fetchall()


def _allocated_amount_for_expense(connection: sqlite3.Connection, expense_id: int) -> float:
    row = connection.execute(
        """
        SELECT COALESCE(SUM(allocated_amount), 0) AS allocated_amount
        FROM expense_invoice_allocations
        WHERE expense_id = ?
        """,
        (expense_id,),
    ).fetchone()
    return round(float(row["allocated_amount"]), 2)


def _allocated_amount_for_invoice_item(connection: sqlite3.Connection, attachment_id: int, invoice_item_index: int) -> float:
    row = connection.execute(
        """
        SELECT COALESCE(SUM(allocated_amount), 0) AS allocated_amount
        FROM expense_invoice_allocations
        WHERE attachment_id = ? AND invoice_item_index = ?
        """,
        (attachment_id, invoice_item_index),
    ).fetchone()
    return round(float(row["allocated_amount"]), 2)


def _invoice_item_allocation_owner(connection: sqlite3.Connection, attachment_id: int, invoice_item_index: int) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT expense_id
        FROM expense_invoice_allocations
        WHERE attachment_id = ? AND invoice_item_index = ?
        LIMIT 1
        """,
        (attachment_id, invoice_item_index),
    ).fetchone()


def serialize_expense(expense, attachments, allocations: list[sqlite3.Row] | None = None, connection=None) -> ExpenseResponse:
    allocation_rows = allocations or []
    allocated_amount = round(sum(float(row["allocated_amount"]) for row in allocation_rows), 2)
    remaining_amount = max(round(float(expense["actual_amount"]) - allocated_amount, 2), 0)
    duplicate_of: list = []
    if expense["has_duplicate"] and connection is not None:
        from app.routers.attachments import find_duplicate_sources

        seen: dict[int, dict] = {}
        all_attachment_ids = {att["id"] for att in attachments}
        for alloc in allocation_rows:
            all_attachment_ids.add(alloc["attachment_id"])
        if all_attachment_ids:
            placeholders = ",".join("?" for _ in all_attachment_ids)
            alloc_attachments = connection.execute(
                f"SELECT id, file_hash, duplicate_count FROM attachments WHERE id IN ({placeholders})",
                tuple(all_attachment_ids),
            ).fetchall()
            for att in alloc_attachments:
                if att["duplicate_count"] > 0:
                    for src in find_duplicate_sources(connection, att["file_hash"], att["id"]):
                        if src.attachment_id not in seen:
                            seen[src.attachment_id] = {"attachment_id": src.attachment_id, "filename": src.filename, "employee_name": src.employee_name}
        duplicate_of = list(seen.values())
    invoice_attachment_rows: list = []
    if connection is not None:
        invoice_attachment_rows = _invoice_attachment_rows_for_expense(connection, expense["id"])
    return ExpenseResponse(
        id=expense["id"],
        employee_name=expense["employee_name"],
        company_entity=expense["company_entity"],
        project_name=expense["project_name"],
        category=expense["category"],
        expense_month=expense["expense_month"],
        actual_amount=expense["actual_amount"],
        invoice_amount=expense["invoice_amount"],
        invoice_buyer=expense["invoice_buyer"],
        invoice_number=expense["invoice_number"],
        invoice_date=expense["invoice_date"],
        invoice_type=expense["invoice_type"],
        is_substitute=bool(expense["is_substitute"]),
        substitute_reason=expense["substitute_reason"],
        note=expense["note"],
        status=expense["status"],
        has_duplicate=bool(expense["has_duplicate"]),
        duplicate_of=duplicate_of,
        allocated_amount=allocated_amount,
        remaining_amount=remaining_amount,
        allocation_count=len(allocation_rows),
        reject_reason=expense["reject_reason"] if "reject_reason" in expense.keys() else "",
        reviewed_at=expense["reviewed_at"] if "reviewed_at" in expense.keys() else "",
        created_at=expense["created_at"],
        attachments=[serialize_attachment(row) for row in attachments],
        allocations=[serialize_allocation(row) for row in allocation_rows],
        invoice_attachments=[serialize_attachment(row) for row in invoice_attachment_rows],
    )


def _delete_file(path_value: str) -> None:
    try:
        Path(path_value).unlink(missing_ok=True)
    except OSError:
        pass


def _validate_amount_reason(is_substitute: bool, actual_amount: float, invoice_amount: float, reason: str) -> None:
    amount_mismatch = round(actual_amount, 2) != round(invoice_amount, 2)
    if is_substitute and not reason:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="替票报销必须填写替票说明")
    if amount_mismatch and not reason:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="发票金额与实际报销金额不一致时必须填写说明")


def _ensure_expense_is_pending(expense: sqlite3.Row) -> None:
    if expense["status"] != "pending":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="已提交记录不能继续修改")


def _reset_expense_to_pending(connection: sqlite3.Connection, expense_id: int, reject_reason: str = "") -> None:
    """撤回/打回：保留发票绑定和佐证材料，状态回 pending"""
    connection.execute(
        """
        UPDATE expenses
        SET status = 'pending',
            reject_reason = CASE WHEN ? != '' THEN ? ELSE reject_reason END
        WHERE id = ?
        """,
        (reject_reason, reject_reason, expense_id),
    )


def _attachment_rows_for_expense(connection: sqlite3.Connection, expense_id: int) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT attachments.*
        FROM attachments
        JOIN expense_attachments ON expense_attachments.attachment_id = attachments.id
        WHERE expense_attachments.expense_id = ?
        UNION
        SELECT * FROM attachments WHERE expense_id = ?
        ORDER BY created_at DESC
        """,
        (expense_id, expense_id),
    ).fetchall()


def _invoice_attachment_rows_for_expense(connection: sqlite3.Connection, expense_id: int) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT attachments.*
        FROM attachments
        JOIN expense_invoice_allocations ON expense_invoice_allocations.attachment_id = attachments.id
        WHERE expense_invoice_allocations.expense_id = ?
        GROUP BY attachments.id
        ORDER BY attachments.created_at DESC
        """,
        (expense_id,),
    ).fetchall()


def _attachment_rows_for_user(connection: sqlite3.Connection, attachment_ids: list[int], user_id: int) -> list[sqlite3.Row]:
    if not attachment_ids:
        return []
    placeholders = ",".join("?" for _ in attachment_ids)
    rows = connection.execute(
        f"""
        SELECT *
        FROM attachments
        WHERE id IN ({placeholders}) AND user_id = ?
        """,
        (*attachment_ids, user_id),
    ).fetchall()
    if len(rows) != len(attachment_ids):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="附件不存在或无权使用")
    return rows


def _link_expense_attachments(connection: sqlite3.Connection, expense_id: int, attachment_ids: list[int]) -> None:
    if not attachment_ids:
        return
    connection.executemany(
        "INSERT OR IGNORE INTO expense_attachments (expense_id, attachment_id) VALUES (?, ?)",
        [(expense_id, attachment_id) for attachment_id in attachment_ids],
    )
    placeholders = ",".join("?" for _ in attachment_ids)
    connection.execute(
        f"""
        UPDATE attachments
        SET expense_id = ?
        WHERE id IN ({placeholders}) AND expense_id IS NULL
        """,
        (expense_id, *attachment_ids),
    )


def _load_expense(connection: sqlite3.Connection, expense_id: int):
    expense = connection.execute(
        """
        SELECT expenses.*, users.employee_name
        FROM expenses
        JOIN users ON users.id = expenses.user_id
        WHERE expenses.id = ?
        """,
        (expense_id,),
    ).fetchone()
    attachments = connection.execute(
        """
        SELECT attachments.*
        FROM attachments
        JOIN expense_attachments ON expense_attachments.attachment_id = attachments.id
        WHERE expense_attachments.expense_id = ?
        UNION
        SELECT * FROM attachments WHERE expense_id = ?
        ORDER BY created_at DESC
        """,
        (expense_id, expense_id),
    ).fetchall()
    allocations = _allocation_rows_for_expense(connection, expense_id)
    return expense, attachments, allocations


def _invoice_item_from_attachment(row: sqlite3.Row, index: int) -> dict[str, Any]:
    result = json.loads(row["ocr_result"] or "{}")
    items = result.get("invoice_items")
    if not isinstance(items, list) or index >= len(items):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="附件中没有对应的票据条目")
    item = items[index]
    if not isinstance(item, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="票据条目格式错误")
    return item


def _invoice_amount(item: dict[str, Any]) -> float:
    amount = item.get("amount")
    if not isinstance(amount, (int, float)) or amount <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="票据未识别到发票金额，不能提交")
    return round(float(amount), 2)


def _invoice_text(item: dict[str, Any], key: str) -> str:
    value = item.get(key)
    return "" if value is None else str(value).strip()


def _invoice_type(item: dict[str, Any]) -> str:
    return _invoice_text(item, "sub_type_description") or _invoice_text(item, "type_description") or "票据"


def _validate_invoice_item(item: dict[str, Any], user_company_entity: str, buyer_confirmed: bool = False) -> None:
    buyer = _invoice_text(item, "buyer")
    if not buyer:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="票据未识别到企业抬头，不能提交")
    match_status = invoice_buyer_match_status(buyer)
    if match_status == "none":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"票据抬头「{buyer}」不在可用公司主体内，不能提交")
    if match_status == "exact" and normalize_company_title(buyer) == normalize_company_title(user_company_entity):
        return
    if buyer_confirmed:
        return
    if match_status == "partial":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"票据抬头「{buyer}」仅部分命中公司主体，请人工确认后再提交")
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"票据抬头「{buyer}」与绑定公司主体不一致，请人工确认后再提交")


def _sync_expense_after_allocation(connection: sqlite3.Connection, expense_id: int) -> None:
    """匹配发票后更新票面合计和替票标记，不改变状态（提交是独立操作）"""
    expense = connection.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()
    if expense is None:
        return
    allocated_amount = _allocated_amount_for_expense(connection, expense_id)
    actual_amount = round(float(expense["actual_amount"]), 2)
    if allocated_amount <= 0:
        connection.execute(
            """
            UPDATE expenses
            SET
                invoice_amount = NULL,
                invoice_buyer = '',
                invoice_number = '',
                invoice_date = '',
                invoice_type = '',
                is_substitute = 0
            WHERE id = ?
            """,
            (expense_id,),
        )
        return
    connection.execute(
        """
        UPDATE expenses
        SET
            invoice_amount = ?,
            is_substitute = CASE WHEN ? THEN 1 ELSE 0 END
        WHERE id = ?
        """,
        (
            allocated_amount if allocated_amount else None,
            int(round(allocated_amount, 2) != actual_amount),
            expense_id,
        ),
    )


def _create_allocation(
    connection: sqlite3.Connection,
    expense: sqlite3.Row,
    attachment: sqlite3.Row,
    invoice_item: dict[str, Any],
    invoice_item_index: int,
    note: str,
    sync: bool = True,
) -> None:
    invoice_amount = _invoice_amount(invoice_item)
    if _invoice_item_allocation_owner(connection, attachment["id"], invoice_item_index) is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="这张发票已经匹配到报销项目")

    existing_expense_allocated = _allocated_amount_for_expense(connection, expense["id"])
    expense_total = round(float(expense["actual_amount"]), 2)
    next_expense_allocated = round(existing_expense_allocated + invoice_amount, 2)
    if next_expense_allocated > expense_total and not note.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="票面合计与花费金额不一致时必须填写说明")

    try:
        connection.execute(
            """
            INSERT INTO expense_invoice_allocations (
                expense_id, attachment_id, invoice_item_index, invoice_amount,
                allocated_amount, invoice_buyer, invoice_number, invoice_date,
                invoice_type, note
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                expense["id"],
                attachment["id"],
                invoice_item_index,
                invoice_amount,
                invoice_amount,
                _invoice_text(invoice_item, "buyer"),
                _invoice_text(invoice_item, "invoice_number"),
                _invoice_text(invoice_item, "date"),
                _invoice_type(invoice_item),
                note.strip(),
            ),
        )
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="这张发票已经匹配到报销项目")

    connection.execute(
        """
        UPDATE expenses
        SET
            invoice_buyer = CASE WHEN invoice_buyer = '' THEN ? ELSE invoice_buyer END,
            invoice_number = CASE WHEN invoice_number = '' THEN ? ELSE invoice_number END,
            invoice_date = CASE WHEN invoice_date = '' THEN ? ELSE invoice_date END,
            invoice_type = CASE WHEN invoice_type = '' THEN ? ELSE invoice_type END,
            substitute_reason = CASE WHEN ? != '' THEN ? ELSE substitute_reason END,
            has_duplicate = CASE WHEN ? THEN 1 ELSE has_duplicate END
        WHERE id = ?
        """,
        (
            _invoice_text(invoice_item, "buyer"),
            _invoice_text(invoice_item, "invoice_number"),
            _invoice_text(invoice_item, "date"),
            _invoice_type(invoice_item),
            note.strip(),
            note.strip(),
            int(attachment["duplicate_count"] > 0),
            expense["id"],
        ),
    )
    if sync:
        _sync_expense_after_allocation(connection, expense["id"])


@router.get("/expenses", response_model=list[ExpenseResponse])
def list_expenses(request: Request, user=Depends(get_current_user)) -> list[ExpenseResponse]:
    with request.app.state.db.connect() as connection:
        rows = connection.execute(
            """
            SELECT expenses.*, users.employee_name
            FROM expenses
            JOIN users ON users.id = expenses.user_id
            WHERE expenses.user_id = ?
            ORDER BY expenses.created_at DESC
            """,
            (user["id"],),
        ).fetchall()
        result = []
        for expense in rows:
            attachments = _attachment_rows_for_expense(connection, expense["id"])
            allocations = _allocation_rows_for_expense(connection, expense["id"])
            result.append(serialize_expense(expense, attachments, allocations, connection))
    return result


@router.get("/invoice-pool", response_model=list[InvoicePoolItem])
def list_invoice_pool(request: Request, user=Depends(get_current_user)) -> list[InvoicePoolItem]:
    with request.app.state.db.connect() as connection:
        attachments = connection.execute(
            """
            SELECT *
            FROM attachments
            WHERE user_id = ?
              AND expense_id IS NULL
              AND pool_status = 'pooled'
              AND created_at >= date('now', '-6 months')
              AND NOT EXISTS (
                  SELECT 1
                  FROM expense_attachments
                  WHERE expense_attachments.attachment_id = attachments.id
              )
            ORDER BY created_at DESC
            """,
            (user["id"],),
        ).fetchall()
        result: list[InvoicePoolItem] = []
        for attachment in attachments:
            ocr_result = json.loads(attachment["ocr_result"] or "{}")
            invoice_items = ocr_result.get("invoice_items")
            if not isinstance(invoice_items, list):
                continue
            for index, item in enumerate(invoice_items):
                if not isinstance(item, dict):
                    continue
                amount = item.get("amount")
                if not isinstance(amount, (int, float)) or amount <= 0:
                    continue
                invoice_amount = round(float(amount), 2)
                allocated_amount = _allocated_amount_for_invoice_item(connection, attachment["id"], index)
                pool_duplicates: list = []
                if attachment["duplicate_count"] > 0:
                    from app.routers.attachments import find_duplicate_sources

                    pool_duplicates = find_duplicate_sources(connection, attachment["file_hash"], attachment["id"])
                result.append(
                    InvoicePoolItem(
                        attachment_id=attachment["id"],
                        attachment_name=attachment["original_filename"],
                        invoice_item_index=index,
                        invoice_amount=invoice_amount,
                        allocated_amount=allocated_amount,
                        remaining_amount=max(round(invoice_amount - allocated_amount, 2), 0),
                        invoice_buyer=_invoice_text(item, "buyer"),
                        invoice_number=_invoice_text(item, "invoice_number"),
                        invoice_date=_invoice_text(item, "date"),
                        invoice_type=_invoice_type(item),
                        ocr_status=attachment["ocr_status"],
                        is_duplicate=attachment["duplicate_count"] > 0,
                        duplicate_of=pool_duplicates,
                        created_at=attachment["created_at"],
                    )
                )
    return result


@router.delete("/expenses/{expense_id}")
def delete_expense(
    expense_id: int,
    request: Request,
    user=Depends(get_current_user),
) -> dict[str, bool]:
    files_to_delete: list[str] = []
    with request.app.state.db.connect() as connection:
        expense = connection.execute(
            "SELECT * FROM expenses WHERE id = ? AND user_id = ?",
            (expense_id, user["id"]),
        ).fetchone()
        if expense is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="花费记录不存在")
        if expense["status"] != "pending":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="只有待处理记录才能删除，已提交请先撤回")

        connection.execute("DELETE FROM expense_invoice_allocations WHERE expense_id = ?", (expense_id,))
        transaction_attachments = _attachment_rows_for_expense(connection, expense_id)
        files_to_delete = [row["stored_path"] for row in transaction_attachments]
        attachment_ids = [row["id"] for row in transaction_attachments]

        connection.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
        if attachment_ids:
            placeholders = ",".join("?" for _ in attachment_ids)
            connection.execute(
                f"DELETE FROM attachments WHERE id IN ({placeholders}) AND user_id = ?",
                (*attachment_ids, user["id"]),
            )

    for path in files_to_delete:
        _delete_file(path)
    return {"deleted": True}


@router.post("/expenses/{expense_id}/withdraw", response_model=ExpenseResponse)
def withdraw_expense(
    expense_id: int,
    request: Request,
    user=Depends(get_current_user),
) -> ExpenseResponse:
    with request.app.state.db.connect() as connection:
        expense = connection.execute(
            "SELECT expenses.*, users.employee_name, users.company_entity FROM expenses JOIN users ON users.id = expenses.user_id WHERE expenses.id = ? AND expenses.user_id = ?",
            (expense_id, user["id"]),
        ).fetchone()
        if expense is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="花费记录不存在")
        if expense["status"] != "matched":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="只有已提交记录才能撤回")
        _reset_expense_to_pending(connection, expense_id)
        updated = connection.execute(
            "SELECT expenses.*, users.employee_name, users.company_entity FROM expenses JOIN users ON users.id = expenses.user_id WHERE expenses.id = ?",
            (expense_id,),
        ).fetchone()
        attachments = _attachment_rows_for_expense(connection, expense_id)
        allocations = _allocation_rows_for_expense(connection, expense_id)
        return serialize_expense(updated, attachments, allocations, connection)


@router.delete("/expenses/{expense_id}/attachments/{attachment_id}", response_model=ExpenseResponse)
def delete_expense_attachment(
    expense_id: int,
    attachment_id: int,
    request: Request,
    user=Depends(get_current_user),
) -> ExpenseResponse:
    deleted_path = ""
    with request.app.state.db.connect() as connection:
        expense = connection.execute(
            "SELECT * FROM expenses WHERE id = ? AND user_id = ?",
            (expense_id, user["id"]),
        ).fetchone()
        if expense is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="花费记录不存在")
        if expense["status"] == "reviewed":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="已完成审核的记录不能删除附件")

        attachment = connection.execute(
            """
            SELECT attachments.*
            FROM attachments
            LEFT JOIN expense_attachments ON expense_attachments.attachment_id = attachments.id
            WHERE attachments.id = ?
              AND attachments.user_id = ?
              AND (attachments.expense_id = ? OR expense_attachments.expense_id = ?)
            """,
            (attachment_id, user["id"], expense_id, expense_id),
        ).fetchone()
        if attachment is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="交易记录附件不存在")

        allocation = connection.execute(
            "SELECT id FROM expense_invoice_allocations WHERE attachment_id = ? LIMIT 1",
            (attachment_id,),
        ).fetchone()
        if allocation is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="已作为发票使用的附件不能从花费记录中删除")

        deleted_path = attachment["stored_path"]
        connection.execute("DELETE FROM attachments WHERE id = ? AND user_id = ?", (attachment_id, user["id"]))
        updated, linked_attachments, allocations = _load_expense(connection, expense_id)

    _delete_file(deleted_path)
    return serialize_expense(updated, linked_attachments, allocations, connection)


@router.delete("/expenses/{expense_id}/invoice-attachments/{attachment_id}", response_model=ExpenseResponse)
def delete_expense_invoice_attachment(
    expense_id: int,
    attachment_id: int,
    request: Request,
    user=Depends(get_current_user),
) -> ExpenseResponse:
    deleted_path = ""
    with request.app.state.db.connect() as connection:
        expense = connection.execute(
            "SELECT * FROM expenses WHERE id = ? AND user_id = ?",
            (expense_id, user["id"]),
        ).fetchone()
        if expense is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="花费记录不存在")
        if expense["status"] == "reviewed":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="已完成审核的记录不能删除发票")
        _ensure_expense_is_pending(expense)

        allocation = connection.execute(
            """
            SELECT id
            FROM expense_invoice_allocations
            WHERE expense_id = ? AND attachment_id = ?
            LIMIT 1
            """,
            (expense_id, attachment_id),
        ).fetchone()
        if allocation is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="发票关联不存在")

        attachment = connection.execute(
            "SELECT * FROM attachments WHERE id = ? AND user_id = ?",
            (attachment_id, user["id"]),
        ).fetchone()
        if attachment is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="发票附件不存在")

        connection.execute(
            "DELETE FROM expense_invoice_allocations WHERE expense_id = ? AND attachment_id = ?",
            (expense_id, attachment_id),
        )
        remaining = connection.execute(
            "SELECT id FROM expense_invoice_allocations WHERE attachment_id = ? LIMIT 1",
            (attachment_id,),
        ).fetchone()
        if remaining is None:
            deleted_path = attachment["stored_path"]
            connection.execute("DELETE FROM attachments WHERE id = ? AND user_id = ?", (attachment_id, user["id"]))

        _sync_expense_after_allocation(connection, expense_id)
        updated, linked_attachments, allocations = _load_expense(connection, expense_id)

    _delete_file(deleted_path)
    return serialize_expense(updated, linked_attachments, allocations, connection)


@router.post("/expense-allocations", response_model=ExpenseResponse)
def create_expense_allocation(
    payload: ExpenseAllocationCreateRequest,
    request: Request,
    user=Depends(get_current_user),
) -> ExpenseResponse:
    with request.app.state.db.connect() as connection:
        expense = connection.execute(
            "SELECT * FROM expenses WHERE id = ? AND user_id = ?",
            (payload.expense_id, user["id"]),
        ).fetchone()
        if expense is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="报销记录不存在")
        _ensure_expense_is_pending(expense)

        attachment = connection.execute(
            "SELECT * FROM attachments WHERE id = ? AND user_id = ?",
            (payload.attachment_id, user["id"]),
        ).fetchone()
        if attachment is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="附件不存在")

        invoice_item = _invoice_item_from_attachment(attachment, payload.invoice_item_index)
        _validate_invoice_item(invoice_item, user["company_entity"], payload.buyer_confirmed)
        _create_allocation(
            connection,
            expense,
            attachment,
            invoice_item,
            payload.invoice_item_index,
            payload.note,
        )
        updated, linked_attachments, allocations = _load_expense(connection, payload.expense_id)
    return serialize_expense(updated, linked_attachments, allocations, connection)


@router.post("/expense-allocations/batch", response_model=ExpenseResponse)
def create_expense_allocations_batch(
    payload: ExpenseAllocationBatchCreateRequest,
    request: Request,
    user=Depends(get_current_user),
) -> ExpenseResponse:
    refs = list({(item.attachment_id, item.invoice_item_index): item for item in payload.invoices}.values())
    with request.app.state.db.connect() as connection:
        expense = connection.execute(
            "SELECT * FROM expenses WHERE id = ? AND user_id = ?",
            (payload.expense_id, user["id"]),
        ).fetchone()
        if expense is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="报销记录不存在")
        _ensure_expense_is_pending(expense)

        invoice_rows: list[tuple[sqlite3.Row, dict[str, Any], int]] = []
        for ref in refs:
            attachment = connection.execute(
                "SELECT * FROM attachments WHERE id = ? AND user_id = ?",
                (ref.attachment_id, user["id"]),
            ).fetchone()
            if attachment is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="附件不存在")
            invoice_item = _invoice_item_from_attachment(attachment, ref.invoice_item_index)
            _validate_invoice_item(invoice_item, user["company_entity"], payload.buyer_confirmed)
            invoice_rows.append((attachment, invoice_item, ref.invoice_item_index))

        existing_total = _allocated_amount_for_expense(connection, expense["id"])
        selected_total = round(sum(_invoice_amount(item) for _, item, _ in invoice_rows), 2)
        next_total = round(existing_total + selected_total, 2)
        actual_amount = round(float(expense["actual_amount"]), 2)
        if next_total > actual_amount and not payload.note.strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="票面合计与花费金额不一致时必须填写说明")

        for attachment, invoice_item, invoice_item_index in invoice_rows:
            _create_allocation(
                connection,
                expense,
                attachment,
                invoice_item,
                invoice_item_index,
                payload.note,
                sync=False,
            )
        _sync_expense_after_allocation(connection, expense["id"])
        updated, linked_attachments, allocations = _load_expense(connection, payload.expense_id)
    return serialize_expense(updated, linked_attachments, allocations, connection)


@router.post("/expenses/{expense_id}/attachments", response_model=ExpenseResponse)
def link_expense_attachments(
    expense_id: int,
    payload: ExpenseAttachmentLinkRequest,
    request: Request,
    user=Depends(get_current_user),
) -> ExpenseResponse:
    attachment_ids = list(dict.fromkeys(payload.attachment_ids))
    with request.app.state.db.connect() as connection:
        expense = connection.execute(
            "SELECT * FROM expenses WHERE id = ? AND user_id = ?",
            (expense_id, user["id"]),
        ).fetchone()
        if expense is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="报销记录不存在")
        if expense["status"] == "reviewed":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="已完成审核的记录不能追加附件")

        attachments = _attachment_rows_for_user(connection, attachment_ids, user["id"])
        allocated = connection.execute(
            f"""
            SELECT COUNT(*) AS count
            FROM expense_invoice_allocations
            WHERE attachment_id IN ({",".join("?" for _ in attachment_ids)})
            """,
            tuple(attachment_ids),
        ).fetchone()
        if allocated["count"] > 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="已作为发票使用的附件不能再作为交易记录")

        _link_expense_attachments(connection, expense_id, [row["id"] for row in attachments])
        updated, linked_attachments, allocations = _load_expense(connection, expense_id)
    return serialize_expense(updated, linked_attachments, allocations, connection)


@router.post("/expenses", response_model=ExpenseResponse)
def create_expense(
    payload: ExpenseCreateRequest,
    request: Request,
    user=Depends(get_current_user),
) -> ExpenseResponse:
    """创建待处理花费"""
    with request.app.state.db.connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO expenses (
                user_id, company_entity, project_name, category, expense_month,
                actual_amount, invoice_amount, is_substitute, substitute_reason,
                note, has_duplicate, status
            )
            VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, 0, 'pending')
            """,
            (
                user["id"],
                user["company_entity"],
                payload.project_name.strip(),
                payload.category.strip() or "差旅交通",
                payload.expense_month,
                payload.actual_amount,
                int(payload.is_substitute),
                payload.substitute_reason.strip(),
                "",
            ),
        )
        expense, linked_attachments, allocations = _load_expense(connection, cursor.lastrowid)
    return serialize_expense(expense, linked_attachments, allocations, connection)


@router.post("/expenses/drafts", response_model=ExpenseResponse)
def create_expense_draft(
    payload: ExpenseCreateRequest,
    request: Request,
    user=Depends(get_current_user),
) -> ExpenseResponse:
    """向后兼容：同 create_expense"""
    return create_expense(payload, request, user)


@router.post("/expenses/submit", response_model=ExpenseResponse)
def create_and_submit_expense(
    payload: ExpenseSubmitRequest,
    request: Request,
    user=Depends(get_current_user),
) -> ExpenseResponse:
    """一次性创建花费 + 绑定发票 + 挂佐证材料 + 直接提交到 matched"""
    with request.app.state.db.connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO expenses (
                user_id, company_entity, project_name, category, expense_month,
                actual_amount, invoice_amount, is_substitute, substitute_reason,
                note, has_duplicate, status
            )
            VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, 0, 'pending')
            """,
            (
                user["id"],
                user["company_entity"],
                payload.project_name.strip(),
                payload.category.strip() or "差旅交通",
                payload.expense_month,
                payload.actual_amount,
                int(payload.is_substitute),
                payload.substitute_reason.strip(),
                "",
            ),
        )
        expense_id = cursor.lastrowid

        # 绑定发票
        if payload.invoices:
            refs = list({(item.attachment_id, item.invoice_item_index): item for item in payload.invoices}.values())
            invoice_rows: list[tuple[sqlite3.Row, dict[str, Any], int]] = []
            for ref in refs:
                attachment = connection.execute(
                    "SELECT * FROM attachments WHERE id = ? AND user_id = ?",
                    (ref.attachment_id, user["id"]),
                ).fetchone()
                if attachment is None:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="附件不存在")
                invoice_item = _invoice_item_from_attachment(attachment, ref.invoice_item_index)
                _validate_invoice_item(invoice_item, user["company_entity"], payload.buyer_confirmed)
                invoice_rows.append((attachment, invoice_item, ref.invoice_item_index))

            expense = connection.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()
            for attachment, invoice_item, invoice_item_index in invoice_rows:
                _create_allocation(
                    connection, expense, attachment, invoice_item, invoice_item_index,
                    payload.note, sync=False,
                )
            _sync_expense_after_allocation(connection, expense_id)

        # 挂佐证材料
        if payload.attachment_ids:
            _link_expense_attachments(connection, expense_id, payload.attachment_ids)

        # 提交
        _submit_expense(connection, expense_id)

        expense, linked_attachments, allocations = _load_expense(connection, expense_id)
    return serialize_expense(expense, linked_attachments, allocations, connection)


def _submit_expense(connection: sqlite3.Connection, expense_id: int) -> None:
    """提交花费：pending → matched"""
    expense = connection.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()
    if expense is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="花费记录不存在")
    if expense["status"] != "pending":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="只有待处理记录才能提交")
    allocated_amount = _allocated_amount_for_expense(connection, expense_id)
    actual_amount = round(float(expense["actual_amount"]), 2)
    if allocated_amount < actual_amount:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="发票金额不足，无法提交")
    connection.execute(
        "UPDATE expenses SET status = 'matched', reject_reason = '' WHERE id = ?",
        (expense_id,),
    )


@router.post("/expenses/{expense_id}/submit", response_model=ExpenseResponse)
def submit_expense(
    expense_id: int,
    request: Request,
    user=Depends(get_current_user),
    payload: PendingExpenseSubmitRequest = Body(default_factory=PendingExpenseSubmitRequest),
) -> ExpenseResponse:
    """提交待处理花费：pending → matched"""
    options = payload
    with request.app.state.db.connect() as connection:
        expense = connection.execute(
            "SELECT * FROM expenses WHERE id = ? AND user_id = ?",
            (expense_id, user["id"]),
        ).fetchone()
        if expense is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="花费记录不存在")
        if expense["status"] != "pending":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="只有待处理记录才能提交")

        is_substitute = bool(expense["is_substitute"]) if options.is_substitute is None else bool(options.is_substitute)
        substitute_reason = (
            str(expense["substitute_reason"] or "")
            if options.substitute_reason is None
            else options.substitute_reason.strip()
        )
        invoice_amount = round(float(expense["invoice_amount"] or 0), 2)
        actual_amount = round(float(expense["actual_amount"]), 2)
        if options.is_substitute is not None or options.substitute_reason is not None:
            _validate_amount_reason(is_substitute, actual_amount, invoice_amount, substitute_reason)
            connection.execute(
                """
                UPDATE expenses
                SET is_substitute = ?, substitute_reason = ?
                WHERE id = ?
                """,
                (int(is_substitute), substitute_reason, expense_id),
            )
        elif is_substitute or round(actual_amount, 2) != round(invoice_amount, 2):
            _validate_amount_reason(is_substitute, actual_amount, invoice_amount, substitute_reason)

        _submit_expense(connection, expense_id)
        expense, linked_attachments, allocations = _load_expense(connection, expense_id)
    return serialize_expense(expense, linked_attachments, allocations, connection)


@router.post("/expenses/batch", response_model=list[ExpenseResponse])
def create_expenses_batch(
    payload: ExpenseBatchCreateRequest,
    request: Request,
    user=Depends(get_current_user),
) -> list[ExpenseResponse]:
    created_ids: list[int] = []

    with request.app.state.db.connect() as connection:
        for item_payload in payload.items:
            attachment = connection.execute(
                "SELECT * FROM attachments WHERE id = ? AND user_id = ?",
                (item_payload.attachment_id, user["id"]),
            ).fetchone()
            if attachment is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="附件不存在")

            invoice_item = _invoice_item_from_attachment(attachment, item_payload.invoice_item_index)
            _validate_invoice_item(invoice_item, user["company_entity"], item_payload.buyer_confirmed)
            invoice_amount = _invoice_amount(invoice_item)
            reason = item_payload.substitute_reason.strip()
            if item_payload.is_substitute:
                if item_payload.actual_amount is None or item_payload.actual_amount <= 0:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="替票必须填写实际报销金额")
                if not reason:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="替票报销必须填写替票说明")
                actual_amount = round(float(item_payload.actual_amount), 2)
            else:
                actual_amount = invoice_amount

            duplicate = connection.execute(
                """
                SELECT id FROM expenses
                WHERE source_attachment_id = ? AND source_invoice_index = ?
                """,
                (item_payload.attachment_id, item_payload.invoice_item_index),
            ).fetchone()
            if duplicate is not None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="票据条目已经提交过")

            cursor = connection.execute(
                """
                INSERT INTO expenses (
                    user_id, company_entity, project_name, category, expense_month, actual_amount,
                    invoice_amount, invoice_buyer, invoice_number, invoice_date, invoice_type,
                    source_attachment_id, source_invoice_index, is_substitute, substitute_reason,
                    note, has_duplicate, status
                )
                VALUES (?, ?, '', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'matched')
                """,
                (
                    user["id"],
                    user["company_entity"],
                    item_payload.category.strip(),
                    item_payload.expense_month,
                    actual_amount,
                    invoice_amount,
                    _invoice_text(invoice_item, "buyer"),
                    _invoice_text(invoice_item, "invoice_number"),
                    _invoice_text(invoice_item, "date"),
                    _invoice_text(invoice_item, "sub_type_description") or _invoice_text(invoice_item, "type_description"),
                    item_payload.attachment_id,
                    item_payload.invoice_item_index,
                    int(item_payload.is_substitute),
                    reason,
                    item_payload.note.strip(),
                    int(attachment["duplicate_count"] > 0),
                ),
            )
            expense_id = cursor.lastrowid
            created_ids.append(expense_id)
            expense = connection.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()
            _create_allocation(
                connection,
                expense,
                attachment,
                invoice_item,
                item_payload.invoice_item_index,
                reason,
            )

        result = []
        for expense_id in created_ids:
            expense, linked_attachments, allocations = _load_expense(connection, expense_id)
            result.append(serialize_expense(expense, linked_attachments, allocations, connection))
    return result
