from __future__ import annotations

import json
import sqlite3
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.dependencies import get_current_user
from app.schemas import (
    AttachmentResponse,
    DraftExpenseCompleteRequest,
    DraftExpenseCreateRequest,
    ExpenseAllocationCreateRequest,
    ExpenseAllocationResponse,
    ExpenseAttachmentLinkRequest,
    ExpenseBatchCreateRequest,
    ExpenseCreateRequest,
    ExpenseResponse,
    InvoicePoolItem,
)


router = APIRouter(prefix="/api", tags=["expenses"])
TITLE_NOISE = re.compile(r"[\s:：,，.。()（）\[\]【】《》<>“”\"']")


def serialize_attachment(row) -> AttachmentResponse:
    return AttachmentResponse(
        id=row["id"],
        original_filename=row["original_filename"],
        file_hash=row["file_hash"],
        file_size=row["file_size"],
        duplicate_count=row["duplicate_count"],
        is_duplicate=row["duplicate_count"] > 0,
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


def serialize_expense(expense, attachments, allocations: list[sqlite3.Row] | None = None) -> ExpenseResponse:
    allocation_rows = allocations or []
    allocated_amount = round(sum(float(row["allocated_amount"]) for row in allocation_rows), 2)
    remaining_amount = max(round(float(expense["actual_amount"]) - allocated_amount, 2), 0)
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
        allocated_amount=allocated_amount,
        remaining_amount=remaining_amount,
        allocation_count=len(allocation_rows),
        created_at=expense["created_at"],
        attachments=[serialize_attachment(row) for row in attachments],
        allocations=[serialize_allocation(row) for row in allocation_rows],
    )


def _validate_expense(payload: ExpenseCreateRequest) -> None:
    reason = payload.substitute_reason.strip()
    invoice_amount = payload.invoice_amount
    amount_mismatch = invoice_amount is not None and round(invoice_amount, 2) != round(payload.actual_amount, 2)
    if payload.is_substitute and not reason:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="替票报销必须填写替票说明")
    if amount_mismatch and not reason:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="发票金额与实际报销金额不一致时必须填写说明")


def _validate_amount_reason(is_substitute: bool, actual_amount: float, invoice_amount: float, reason: str) -> None:
    amount_mismatch = round(actual_amount, 2) != round(invoice_amount, 2)
    if is_substitute and not reason:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="替票报销必须填写替票说明")
    if amount_mismatch and not reason:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="发票金额与实际报销金额不一致时必须填写说明")


def company_titles_match(recognized_buyer: str, expected_company: str) -> bool:
    recognized = _normalize_company_title(recognized_buyer)
    expected = _normalize_company_title(expected_company)
    if not recognized or not expected:
        return False
    return recognized == expected or recognized in expected or expected in recognized


def _normalize_company_title(value: str) -> str:
    value = value.replace("购买方", "").replace("付款方", "").replace("名称", "")
    return TITLE_NOISE.sub("", value)


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


def _validate_invoice_item(item: dict[str, Any], expected_company: str) -> None:
    buyer = _invoice_text(item, "buyer")
    if not buyer:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="票据未识别到企业抬头，不能提交")
    if not company_titles_match(buyer, expected_company):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="票据抬头与员工绑定企业不一致，不能提交")


def _sync_expense_after_allocation(connection: sqlite3.Connection, expense_id: int) -> None:
    expense = connection.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()
    if expense is None:
        return
    allocated_amount = _allocated_amount_for_expense(connection, expense_id)
    is_complete = allocated_amount >= round(float(expense["actual_amount"]), 2)
    connection.execute(
        """
        UPDATE expenses
        SET
            invoice_amount = ?,
            is_substitute = CASE WHEN ? THEN is_substitute ELSE 1 END,
            status = ?
        WHERE id = ?
        """,
        (
            allocated_amount if allocated_amount else None,
            int(is_complete),
            "submitted" if is_complete else "draft",
            expense_id,
        ),
    )


def _create_allocation(
    connection: sqlite3.Connection,
    expense: sqlite3.Row,
    attachment: sqlite3.Row,
    invoice_item: dict[str, Any],
    invoice_item_index: int,
    allocated_amount: float,
    note: str,
) -> None:
    invoice_amount = _invoice_amount(invoice_item)
    existing_invoice_allocated = _allocated_amount_for_invoice_item(connection, attachment["id"], invoice_item_index)
    if round(existing_invoice_allocated + allocated_amount, 2) > invoice_amount:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="发票分摊金额不能超过票面金额")

    existing_expense_allocated = _allocated_amount_for_expense(connection, expense["id"])
    expense_total = round(float(expense["actual_amount"]), 2)
    if round(existing_expense_allocated + allocated_amount, 2) > expense_total:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="分摊金额不能超过报销金额")

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
                round(float(allocated_amount), 2),
                _invoice_text(invoice_item, "buyer"),
                _invoice_text(invoice_item, "invoice_number"),
                _invoice_text(invoice_item, "date"),
                _invoice_type(invoice_item),
                note.strip(),
            ),
        )
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="这张发票已经分摊给该报销记录")

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
            result.append(serialize_expense(expense, attachments, allocations))
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
                        created_at=attachment["created_at"],
                    )
                )
    return result


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

        attachment = connection.execute(
            "SELECT * FROM attachments WHERE id = ? AND user_id = ?",
            (payload.attachment_id, user["id"]),
        ).fetchone()
        if attachment is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="附件不存在")

        invoice_item = _invoice_item_from_attachment(attachment, payload.invoice_item_index)
        _validate_invoice_item(invoice_item, user["company_entity"])
        _create_allocation(
            connection,
            expense,
            attachment,
            invoice_item,
            payload.invoice_item_index,
            round(float(payload.allocated_amount), 2),
            payload.note,
        )
        updated, linked_attachments, allocations = _load_expense(connection, payload.expense_id)
    return serialize_expense(updated, linked_attachments, allocations)


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
    return serialize_expense(updated, linked_attachments, allocations)


@router.post("/expenses", response_model=ExpenseResponse)
def create_expense(
    payload: ExpenseCreateRequest,
    request: Request,
    user=Depends(get_current_user),
) -> ExpenseResponse:
    _validate_expense(payload)
    attachment_ids = list(dict.fromkeys(payload.attachment_ids))

    with request.app.state.db.connect() as connection:
        attachments = _attachment_rows_for_user(connection, attachment_ids, user["id"])

        has_duplicate = any(row["duplicate_count"] > 0 for row in attachments)
        cursor = connection.execute(
            """
            INSERT INTO expenses (
                user_id, company_entity, project_name, category, expense_month, actual_amount,
                invoice_amount, is_substitute, substitute_reason, note, has_duplicate, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'submitted')
            """,
            (
                user["id"],
                user["company_entity"],
                payload.project_name.strip(),
                payload.category.strip(),
                payload.expense_month,
                payload.actual_amount,
                payload.invoice_amount,
                int(payload.is_substitute),
                payload.substitute_reason.strip(),
                payload.note.strip(),
                int(has_duplicate),
            ),
        )
        expense_id = cursor.lastrowid
        if attachment_ids:
            _link_expense_attachments(connection, expense_id, attachment_ids)
        expense, linked_attachments, allocations = _load_expense(connection, expense_id)
    return serialize_expense(expense, linked_attachments, allocations)


@router.post("/expenses/drafts", response_model=ExpenseResponse)
def create_expense_draft(
    payload: DraftExpenseCreateRequest,
    request: Request,
    user=Depends(get_current_user),
) -> ExpenseResponse:
    with request.app.state.db.connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO expenses (
                user_id, company_entity, project_name, category, expense_month,
                actual_amount, invoice_amount, is_substitute, substitute_reason,
                note, has_duplicate, status
            )
            VALUES (?, ?, ?, ?, ?, ?, NULL, 0, '', ?, 0, 'draft')
            """,
            (
                user["id"],
                user["company_entity"],
                payload.project_name.strip(),
                payload.category.strip() or "差旅交通",
                payload.expense_month,
                payload.actual_amount,
                "",
            ),
        )
        expense, linked_attachments, allocations = _load_expense(connection, cursor.lastrowid)
    return serialize_expense(expense, linked_attachments, allocations)


@router.post("/expenses/drafts/{expense_id}/complete", response_model=ExpenseResponse)
def complete_expense_draft(
    expense_id: int,
    payload: DraftExpenseCompleteRequest,
    request: Request,
    user=Depends(get_current_user),
) -> ExpenseResponse:
    with request.app.state.db.connect() as connection:
        draft = connection.execute(
            "SELECT * FROM expenses WHERE id = ? AND user_id = ? AND status = 'draft'",
            (expense_id, user["id"]),
        ).fetchone()
        if draft is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="待补材料记录不存在")

        attachment = connection.execute(
            "SELECT * FROM attachments WHERE id = ? AND user_id = ?",
            (payload.attachment_id, user["id"]),
        ).fetchone()
        if attachment is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="附件不存在")

        invoice_item = _invoice_item_from_attachment(attachment, payload.invoice_item_index)
        _validate_invoice_item(invoice_item, user["company_entity"])
        invoice_amount = _invoice_amount(invoice_item)
        actual_amount = round(float(payload.actual_amount), 2)
        reason = payload.substitute_reason.strip()
        _validate_amount_reason(payload.is_substitute, actual_amount, invoice_amount, reason)

        connection.execute(
            """
            UPDATE expenses
            SET
                category = ?,
                expense_month = ?,
                actual_amount = ?,
                is_substitute = ?,
                substitute_reason = ?,
                note = ?,
                has_duplicate = ?,
                status = 'draft'
            WHERE id = ?
            """,
            (
                payload.category.strip(),
                payload.expense_month,
                actual_amount,
                int(payload.is_substitute),
                reason,
                payload.note.strip() or draft["note"],
                int(attachment["duplicate_count"] > 0),
                expense_id,
            ),
        )
        updated = connection.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()
        _create_allocation(
            connection,
            updated,
            attachment,
            invoice_item,
            payload.invoice_item_index,
            actual_amount,
            reason,
        )
        expense, linked_attachments, allocations = _load_expense(connection, expense_id)
    return serialize_expense(expense, linked_attachments, allocations)


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
            _validate_invoice_item(invoice_item, user["company_entity"])
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
                VALUES (?, ?, '', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'submitted')
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
                actual_amount,
                reason,
            )

        result = []
        for expense_id in created_ids:
            expense, linked_attachments, allocations = _load_expense(connection, expense_id)
            result.append(serialize_expense(expense, linked_attachments, allocations))
    return result
