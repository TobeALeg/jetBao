from __future__ import annotations

import secrets
import sqlite3
from io import BytesIO
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from openpyxl import Workbook

from app.company_entities import is_allowed_company_entity, normalize_company_entity
from app.dependencies import require_admin
from app.expense_month_filter import expense_period_label
from app.schemas import AdminUserCreateRequest, AdminUserResponse, AdminUserUpdateRequest, ExpenseBulkApproveResponse, ExpenseRejectRequest, ExpenseResponse, ExpenseReviewDetailResponse, ExportPreview, LedgerRow
from app.security import hash_password
from app.services.export_package import build_export_package
from app.services.ledger import build_ledger_query, load_ledger_duplicate_sources, serialize_ledger_row


router = APIRouter(prefix="/api/admin", tags=["admin"])


def _validate_company_entity(company_entity: str) -> str:
    company = normalize_company_entity(company_entity)
    if not is_allowed_company_entity(company):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="公司主体不在可选范围内")
    return company


def _normalize_enterprise_email(email: str | None, expected_domain: str) -> str | None:
    normalized = email.strip().lower() if email else None
    if not normalized:
        return None
    local_part, separator, domain = normalized.rpartition("@")
    if not separator or not local_part or domain != expected_domain:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"企业邮箱必须使用 @{expected_domain}",
        )
    return normalized


@router.get("/ledger", response_model=list[LedgerRow])
def ledger(
    request: Request,
    month: str | None = None,
    year: str | None = None,
    month_part: str | None = None,
    company_entity: str | None = None,
    employee: str | None = None,
    category: str | None = None,
    is_substitute: bool | None = Query(default=None),
    has_duplicate: bool | None = Query(default=None),
    record_status: str | None = Query(default=None, alias="status"),
    admin=Depends(require_admin),
) -> list[LedgerRow]:
    query, params = build_ledger_query(
        month=month,
        company_entity=company_entity,
        employee=employee,
        category=category,
        is_substitute=is_substitute,
        has_duplicate=has_duplicate,
        record_status=record_status,
        year=year,
        month_part=month_part,
    )
    with request.app.state.db.connect() as connection:
        rows = connection.execute(query, params).fetchall()
        return [
            serialize_ledger_row(
                row,
                load_ledger_duplicate_sources(connection, row["id"])
                if row["has_duplicate"]
                else [],
            )
            for row in rows
        ]


@router.get("/export/preview", response_model=ExportPreview)
def export_preview(
    request: Request,
    month: str | None = None,
    year: str | None = None,
    month_part: str | None = None,
    company_entity: str | None = None,
    admin=Depends(require_admin),
) -> ExportPreview:
    query, params = build_ledger_query(
        month=month,
        year=year,
        month_part=month_part,
        company_entity=company_entity,
        employee=None,
        category=None,
        is_substitute=None,
        has_duplicate=None,
        record_status="matched",
    )
    pending_query, pending_params = build_ledger_query(
        month=month,
        year=year,
        month_part=month_part,
        company_entity=company_entity,
        employee=None,
        category=None,
        is_substitute=None,
        has_duplicate=None,
        record_status="pending",
    )
    with request.app.state.db.connect() as connection:
        rows = connection.execute(query, params).fetchall()
        pending_rows = connection.execute(pending_query, pending_params).fetchall()
    employee_count = len({row["employee_name"] for row in rows})
    total_amount = round(sum(float(row["actual_amount"]) for row in rows), 2)
    return ExportPreview(
        employee_count=employee_count,
        record_count=len(rows),
        total_amount=total_amount,
        pending_count=len(pending_rows),
    )


@router.get("/export.xlsx")
def export_excel(
    request: Request,
    month: str | None = None,
    year: str | None = None,
    month_part: str | None = None,
    company_entity: str | None = None,
    admin=Depends(require_admin),
) -> StreamingResponse:
    query, params = build_ledger_query(
        month=month,
        year=year,
        month_part=month_part,
        company_entity=company_entity,
        employee=None,
        category=None,
        is_substitute=None,
        has_duplicate=None,
        record_status="matched",
    )
    with request.app.state.db.connect() as connection:
        rows = connection.execute(query, params).fetchall()

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "报销台账"
    headers = [
        "公司主体",
        "员工",
        "项目",
        "类别",
        "报销月份",
        "实际报销金额",
        "发票金额",
        "发票抬头",
        "发票号码",
        "发票日期",
        "是否替票",
        "说明",
        "提交时间",
        "交易记录附件",
        "发票分摊",
    ]
    sheet.append(headers)
    for row in rows:
        sheet.append(
            [
                row["company_entity"],
                row["employee_name"],
                row["project_name"],
                row["category"],
                row["expense_month"],
                row["actual_amount"],
                row["invoice_amount"],
                row["invoice_buyer"],
                row["invoice_number"],
                row["invoice_date"],
                "是" if row["is_substitute"] else "否",
                row["substitute_reason"] or row["note"],
                row["created_at"],
                row["attachment_names"],
                row["allocation_summary"],
            ]
        )

    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    filename = f"expense-ledger-{expense_period_label(month, year, month_part)}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export-package.zip")
def export_package(
    request: Request,
    month: str | None = None,
    year: str | None = None,
    month_part: str | None = None,
    company_entity: str | None = None,
    admin=Depends(require_admin),
) -> StreamingResponse:
    with request.app.state.db.connect() as connection:
        output, filename = build_export_package(connection, month, company_entity, year=year, month_part=month_part)
    encoded_filename = quote(filename)
    return StreamingResponse(
        output,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"},
    )


def _serialize_user(row) -> AdminUserResponse:
    return AdminUserResponse(
        id=row["id"],
        username=row["username"],
        email=row["email"],
        identity_id=row["identity_id"],
        role=row["role"],
        employee_name=row["employee_name"],
        company_entity=row["company_entity"],
        is_active=bool(row["is_active"]),
        created_at=row["created_at"],
    )


@router.get("/users", response_model=list[AdminUserResponse])
def list_users(request: Request, admin=Depends(require_admin)) -> list[AdminUserResponse]:
    with request.app.state.db.connect() as connection:
        rows = connection.execute("SELECT * FROM users ORDER BY is_active DESC, created_at DESC").fetchall()
    return [_serialize_user(row) for row in rows]


@router.post("/users", response_model=AdminUserResponse)
def create_user(payload: AdminUserCreateRequest, request: Request, admin=Depends(require_admin)) -> AdminUserResponse:
    company_entity = _validate_company_entity(payload.company_entity)
    email = _normalize_enterprise_email(payload.email, request.app.state.settings.sso_email_domain)
    if request.app.state.settings.auth_mode in {"hybrid", "sso"} and not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="启用统一登录后必须填写企业邮箱")
    if request.app.state.settings.auth_mode != "sso" and not payload.password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="迁移期间创建账号仍需设置初始密码")
    password = payload.password or secrets.token_urlsafe(32)
    with request.app.state.db.connect() as connection:
        existing = connection.execute("SELECT id FROM users WHERE username = ?", (payload.username.strip(),)).fetchone()
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户名已存在")
        try:
            cursor = connection.execute(
                """
                INSERT INTO users (username, email, password_hash, role, employee_name, company_entity, is_active)
                VALUES (?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    payload.username.strip(),
                    email,
                    hash_password(password),
                    payload.role,
                    payload.employee_name.strip(),
                    company_entity,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="企业邮箱已绑定其他员工") from exc
        row = connection.execute("SELECT * FROM users WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return _serialize_user(row)


@router.patch("/users/{user_id}", response_model=AdminUserResponse)
def update_user(
    user_id: int,
    payload: AdminUserUpdateRequest,
    request: Request,
    admin=Depends(require_admin),
) -> AdminUserResponse:
    if user_id == admin["id"] and payload.is_active is False:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能停用当前登录账号")

    with request.app.state.db.connect() as connection:
        row = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

        fields: list[str] = []
        params: list[object] = []
        if payload.email is not None:
            normalized_email = _normalize_enterprise_email(
                payload.email,
                request.app.state.settings.sso_email_domain,
            )
            if row["identity_id"] and normalized_email != row["email"]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="企业邮箱已绑定统一身份，不能直接修改",
                )
            fields.append("email = ?")
            params.append(normalized_email)
        if payload.password:
            fields.append("password_hash = ?")
            params.append(hash_password(payload.password))
        if payload.role is not None:
            fields.append("role = ?")
            params.append(payload.role)
        if payload.employee_name is not None:
            fields.append("employee_name = ?")
            params.append(payload.employee_name.strip())
        if payload.company_entity is not None:
            fields.append("company_entity = ?")
            params.append(_validate_company_entity(payload.company_entity))
        if payload.is_active is not None:
            fields.append("is_active = ?")
            params.append(int(payload.is_active))

        if fields:
            params.append(user_id)
            try:
                connection.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = ?", params)
            except sqlite3.IntegrityError as exc:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="企业邮箱已绑定其他员工") from exc
        updated = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _serialize_user(updated)


@router.delete("/users/{user_id}", response_model=AdminUserResponse)
def deactivate_user(user_id: int, request: Request, admin=Depends(require_admin)) -> AdminUserResponse:
    if user_id == admin["id"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能停用当前登录账号")
    with request.app.state.db.connect() as connection:
        row = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
        connection.execute("UPDATE users SET is_active = 0 WHERE id = ?", (user_id,))
        updated = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _serialize_user(updated)


@router.get("/expenses/{expense_id}", response_model=ExpenseReviewDetailResponse)
def get_expense_for_review(
    expense_id: int,
    request: Request,
    admin=Depends(require_admin),
) -> ExpenseReviewDetailResponse:
    from app.routers.expenses import (
        _allocation_rows_for_expense,
        _attachment_rows_for_expense,
        serialize_expense,
    )

    with request.app.state.db.connect() as connection:
        expense = connection.execute(
            """
            SELECT expenses.*, users.employee_name, users.company_entity
            FROM expenses
            JOIN users ON users.id = expenses.user_id
            WHERE expenses.id = ?
            """,
            (expense_id,),
        ).fetchone()
        if expense is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="花费记录不存在")
        attachments = _attachment_rows_for_expense(connection, expense_id)
        allocations = _allocation_rows_for_expense(connection, expense_id)
        return serialize_expense(expense, attachments, allocations, connection)


@router.post("/expense-reviews/approve-all", response_model=ExpenseBulkApproveResponse)
def approve_all_expenses(
    request: Request,
    month: str | None = None,
    year: str | None = None,
    month_part: str | None = None,
    company_entity: str | None = None,
    employee: str | None = None,
    category: str | None = None,
    is_substitute: bool | None = Query(default=None),
    has_duplicate: bool | None = Query(default=None),
    record_status: str | None = Query(default=None, alias="status"),
    admin=Depends(require_admin),
) -> ExpenseBulkApproveResponse:
    """审核当前台账筛选范围内的全部已提交记录。"""
    from datetime import datetime, timezone

    # 状态筛选本身没有包含待审核记录时，不应扩大用户当前看到的范围。
    if record_status and record_status != "matched":
        return ExpenseBulkApproveResponse(approved_count=0)

    query, params = build_ledger_query(
        month=month,
        company_entity=company_entity,
        employee=employee,
        category=category,
        is_substitute=is_substitute,
        has_duplicate=has_duplicate,
        record_status="matched",
        year=year,
        month_part=month_part,
    )
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with request.app.state.db.connect() as connection:
        cursor = connection.execute(
            f"""
            UPDATE expenses
            SET status = 'reviewed', reviewed_at = ?, reject_reason = ''
            WHERE status = 'matched'
              AND id IN (SELECT id FROM ({query}))
            """,
            [now, *params],
        )
        approved_count = cursor.rowcount
    return ExpenseBulkApproveResponse(approved_count=approved_count)


@router.post("/expenses/{expense_id}/reject", response_model=ExpenseResponse)
def reject_expense(
    expense_id: int,
    request: Request,
    payload: ExpenseRejectRequest = ExpenseRejectRequest(),
    admin=Depends(require_admin),
) -> ExpenseResponse:
    from app.routers.expenses import _allocation_rows_for_expense, _attachment_rows_for_expense, _reset_expense_to_pending, serialize_expense

    with request.app.state.db.connect() as connection:
        expense = connection.execute(
            "SELECT expenses.*, users.employee_name, users.company_entity FROM expenses JOIN users ON users.id = expenses.user_id WHERE expenses.id = ?",
            (expense_id,),
        ).fetchone()
        if expense is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="花费记录不存在")
        if expense["status"] != "matched":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="只有已提交记录才能打回")
        _reset_expense_to_pending(connection, expense_id, reject_reason=payload.reason.strip())
        updated = connection.execute(
            "SELECT expenses.*, users.employee_name, users.company_entity FROM expenses JOIN users ON users.id = expenses.user_id WHERE expenses.id = ?",
            (expense_id,),
        ).fetchone()
        attachments = _attachment_rows_for_expense(connection, expense_id)
        allocations = _allocation_rows_for_expense(connection, expense_id)
        return serialize_expense(updated, attachments, allocations, connection)


@router.post("/expenses/{expense_id}/approve", response_model=ExpenseResponse)
def approve_expense(
    expense_id: int,
    request: Request,
    admin=Depends(require_admin),
) -> ExpenseResponse:
    from app.routers.expenses import _allocation_rows_for_expense, _attachment_rows_for_expense, serialize_expense
    from datetime import datetime, timezone

    with request.app.state.db.connect() as connection:
        expense = connection.execute(
            "SELECT expenses.*, users.employee_name, users.company_entity FROM expenses JOIN users ON users.id = expenses.user_id WHERE expenses.id = ?",
            (expense_id,),
        ).fetchone()
        if expense is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="花费记录不存在")
        if expense["status"] != "matched":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="只有已提交记录才能审核通过")
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        connection.execute(
            "UPDATE expenses SET status = 'reviewed', reviewed_at = ?, reject_reason = '' WHERE id = ?",
            (now, expense_id),
        )
        updated = connection.execute(
            "SELECT expenses.*, users.employee_name, users.company_entity FROM expenses JOIN users ON users.id = expenses.user_id WHERE expenses.id = ?",
            (expense_id,),
        ).fetchone()
        attachments = _attachment_rows_for_expense(connection, expense_id)
        allocations = _allocation_rows_for_expense(connection, expense_id)
        return serialize_expense(updated, attachments, allocations, connection)


@router.post("/expenses/{expense_id}/unreview", response_model=ExpenseResponse)
def unreview_expense(
    expense_id: int,
    request: Request,
    admin=Depends(require_admin),
) -> ExpenseResponse:
    from app.routers.expenses import _allocation_rows_for_expense, _attachment_rows_for_expense, serialize_expense

    with request.app.state.db.connect() as connection:
        expense = connection.execute(
            "SELECT expenses.*, users.employee_name, users.company_entity FROM expenses JOIN users ON users.id = expenses.user_id WHERE expenses.id = ?",
            (expense_id,),
        ).fetchone()
        if expense is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="花费记录不存在")
        if expense["status"] != "reviewed":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="只有已完成审核的记录才能撤销")
        connection.execute(
            "UPDATE expenses SET status = 'matched', reviewed_at = '' WHERE id = ?",
            (expense_id,),
        )
        updated = connection.execute(
            "SELECT expenses.*, users.employee_name, users.company_entity FROM expenses JOIN users ON users.id = expenses.user_id WHERE expenses.id = ?",
            (expense_id,),
        ).fetchone()
        attachments = _attachment_rows_for_expense(connection, expense_id)
        allocations = _allocation_rows_for_expense(connection, expense_id)
        return serialize_expense(updated, attachments, allocations, connection)
