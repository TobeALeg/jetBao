from __future__ import annotations

import json
import sqlite3
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.dependencies import get_current_user
from app.schemas import AttachmentResponse, ExpenseBatchCreateRequest, ExpenseCreateRequest, ExpenseResponse


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


def serialize_expense(expense, attachments) -> ExpenseResponse:
    return ExpenseResponse(
        id=expense["id"],
        employee_name=expense["employee_name"],
        company_entity=expense["company_entity"],
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
        created_at=expense["created_at"],
        attachments=[serialize_attachment(row) for row in attachments],
    )


def _validate_expense(payload: ExpenseCreateRequest) -> None:
    reason = payload.substitute_reason.strip()
    invoice_amount = payload.invoice_amount
    amount_mismatch = invoice_amount is not None and round(invoice_amount, 2) != round(payload.actual_amount, 2)
    if payload.is_substitute and not reason:
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
    return expense, attachments


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


def _validate_invoice_item(item: dict[str, Any], expected_company: str) -> None:
    buyer = _invoice_text(item, "buyer")
    if not buyer:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="票据未识别到企业抬头，不能提交")
    if not company_titles_match(buyer, expected_company):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="票据抬头与员工绑定企业不一致，不能提交")


@router.get("/expenses", response_model=list[ExpenseResponse])
def list_expenses(request: Request, user=Depends(get_current_user)) -> list[ExpenseResponse]:
    params: tuple[int, ...] | tuple[()] = ()
    where = ""
    if user["role"] != "admin":
        where = "WHERE expenses.user_id = ?"
        params = (user["id"],)
    with request.app.state.db.connect() as connection:
        rows = connection.execute(
            f"""
            SELECT expenses.*, users.employee_name
            FROM expenses
            JOIN users ON users.id = expenses.user_id
            {where}
            ORDER BY expenses.created_at DESC
            """,
            params,
        ).fetchall()
        result = []
        for expense in rows:
            attachments = connection.execute(
                "SELECT * FROM attachments WHERE expense_id = ? ORDER BY created_at DESC",
                (expense["id"],),
            ).fetchall()
            result.append(serialize_expense(expense, attachments))
    return result


@router.post("/expenses", response_model=ExpenseResponse)
def create_expense(
    payload: ExpenseCreateRequest,
    request: Request,
    user=Depends(get_current_user),
) -> ExpenseResponse:
    _validate_expense(payload)
    attachment_ids = list(dict.fromkeys(payload.attachment_ids))

    with request.app.state.db.connect() as connection:
        attachments = []
        if attachment_ids:
            placeholders = ",".join("?" for _ in attachment_ids)
            attachments = connection.execute(
                f"""
                SELECT * FROM attachments
                WHERE id IN ({placeholders}) AND user_id = ?
                """,
                (*attachment_ids, user["id"]),
            ).fetchall()
            if len(attachments) != len(attachment_ids):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="附件不存在或已被使用")

        has_duplicate = any(row["duplicate_count"] > 0 for row in attachments)
        cursor = connection.execute(
            """
            INSERT INTO expenses (
                user_id, company_entity, category, expense_month, actual_amount,
                invoice_amount, is_substitute, substitute_reason, note, has_duplicate
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user["id"],
                user["company_entity"],
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
            placeholders = ",".join("?" for _ in attachment_ids)
            connection.executemany(
                "INSERT OR IGNORE INTO expense_attachments (expense_id, attachment_id) VALUES (?, ?)",
                [(expense_id, attachment_id) for attachment_id in attachment_ids],
            )
            connection.execute(f"UPDATE attachments SET expense_id = ? WHERE id IN ({placeholders}) AND expense_id IS NULL", (expense_id, *attachment_ids))
        expense, linked_attachments = _load_expense(connection, expense_id)
    return serialize_expense(expense, linked_attachments)


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
                    user_id, company_entity, category, expense_month, actual_amount,
                    invoice_amount, invoice_buyer, invoice_number, invoice_date, invoice_type,
                    source_attachment_id, source_invoice_index, is_substitute, substitute_reason,
                    note, has_duplicate
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            connection.execute(
                "INSERT OR IGNORE INTO expense_attachments (expense_id, attachment_id) VALUES (?, ?)",
                (expense_id, item_payload.attachment_id),
            )

        result = []
        for expense_id in created_ids:
            expense, linked_attachments = _load_expense(connection, expense_id)
            result.append(serialize_expense(expense, linked_attachments))
    return result
