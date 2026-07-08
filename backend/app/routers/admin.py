from __future__ import annotations

from io import BytesIO
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from openpyxl import Workbook

from app.company_entities import is_allowed_company_entity, normalize_company_entity
from app.dependencies import require_admin
from app.schemas import AdminUserCreateRequest, AdminUserResponse, AdminUserUpdateRequest, ExpenseRejectRequest, ExpenseResponse, ExportPreview, LedgerRow
from app.security import hash_password
from app.services.export_package import build_export_package


router = APIRouter(prefix="/api/admin", tags=["admin"])


def _validate_company_entity(company_entity: str) -> str:
    company = normalize_company_entity(company_entity)
    if not is_allowed_company_entity(company):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="公司主体不在可选范围内")
    return company


def _ledger_query(
    month: str | None,
    company_entity: str | None,
    employee: str | None,
    category: str | None,
    is_substitute: bool | None,
    has_duplicate: bool | None,
    record_status: str | None,
) -> tuple[str, list[object]]:
    where = []
    params: list[object] = []
    if month:
        where.append("expenses.expense_month = ?")
        params.append(month)
    if company_entity:
        where.append("expenses.company_entity = ?")
        params.append(company_entity)
    if employee:
        where.append("users.employee_name LIKE ?")
        params.append(f"%{employee}%")
    if category:
        where.append("expenses.category = ?")
        params.append(category)
    if is_substitute is not None:
        where.append("expenses.is_substitute = ?")
        params.append(int(is_substitute))
    if has_duplicate is not None:
        where.append("expenses.has_duplicate = ?")
        params.append(int(has_duplicate))
    if record_status:
        where.append("expenses.status = ?")
        params.append(record_status)

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    query = f"""
        SELECT
            expenses.id,
            expenses.company_entity,
            users.employee_name,
            expenses.project_name,
            expenses.category,
            expenses.expense_month,
            expenses.actual_amount,
            expenses.invoice_amount,
            expenses.invoice_buyer,
            expenses.invoice_number,
            expenses.invoice_date,
            expenses.invoice_type,
            expenses.is_substitute,
            expenses.substitute_reason,
            expenses.note,
            expenses.status,
            expenses.has_duplicate,
            expenses.created_at,
            COALESCE((
                SELECT GROUP_CONCAT(attachments.original_filename, '、')
                FROM expense_attachments
                JOIN attachments ON attachments.id = expense_attachments.attachment_id
                WHERE expense_attachments.expense_id = expenses.id
            ), '') AS attachment_names,
            COALESCE((
                SELECT GROUP_CONCAT(
                    CASE
                        WHEN expense_invoice_allocations.invoice_number != ''
                        THEN expense_invoice_allocations.invoice_number
                        ELSE '发票'
                    END || ':' || expense_invoice_allocations.allocated_amount,
                    '、'
                )
                FROM expense_invoice_allocations
                WHERE expense_invoice_allocations.expense_id = expenses.id
            ), '') AS allocation_summary
        FROM expenses
        JOIN users ON users.id = expenses.user_id
        {where_sql}
        ORDER BY expenses.created_at DESC
    """
    return query, params


def _serialize_ledger_row(row, connection=None) -> LedgerRow:
    ledger_duplicates: list = []
    if row["has_duplicate"] and connection is not None:
        from app.routers.attachments import find_duplicate_sources

        attachments = connection.execute(
            """
            SELECT a.id, a.file_hash, a.duplicate_count
            FROM attachments a
            JOIN expense_invoice_allocations ea ON ea.attachment_id = a.id
            WHERE ea.expense_id = ?
            """,
            (row["id"],),
        ).fetchall()
        seen: dict[int, dict] = {}
        for att in attachments:
            if att["duplicate_count"] > 0:
                for src in find_duplicate_sources(connection, att["file_hash"], att["id"]):
                    if src.attachment_id not in seen:
                        seen[src.attachment_id] = {"attachment_id": src.attachment_id, "filename": src.filename, "employee_name": src.employee_name}
        ledger_duplicates = list(seen.values())
    return LedgerRow(
        id=row["id"],
        company_entity=row["company_entity"],
        employee_name=row["employee_name"],
        project_name=row["project_name"],
        category=row["category"],
        expense_month=row["expense_month"],
        actual_amount=row["actual_amount"],
        invoice_amount=row["invoice_amount"],
        invoice_buyer=row["invoice_buyer"],
        invoice_number=row["invoice_number"],
        invoice_date=row["invoice_date"],
        invoice_type=row["invoice_type"],
        is_substitute=bool(row["is_substitute"]),
        substitute_reason=row["substitute_reason"],
        note=row["note"],
        status=row["status"],
        has_duplicate=bool(row["has_duplicate"]),
        duplicate_of=ledger_duplicates,
        reject_reason=row["reject_reason"] if "reject_reason" in row.keys() else "",
        reviewed_at=row["reviewed_at"] if "reviewed_at" in row.keys() else "",
        created_at=row["created_at"],
        attachment_names=row["attachment_names"],
        allocation_summary=row["allocation_summary"],
    )


@router.get("/ledger", response_model=list[LedgerRow])
def ledger(
    request: Request,
    month: str | None = None,
    company_entity: str | None = None,
    employee: str | None = None,
    category: str | None = None,
    is_substitute: bool | None = Query(default=None),
    has_duplicate: bool | None = Query(default=None),
    record_status: str | None = Query(default=None, alias="status"),
    admin=Depends(require_admin),
) -> list[LedgerRow]:
    query, params = _ledger_query(month, company_entity, employee, category, is_substitute, has_duplicate, record_status)
    with request.app.state.db.connect() as connection:
        rows = connection.execute(query, params).fetchall()
    return [_serialize_ledger_row(row, connection) for row in rows]


@router.get("/export/preview", response_model=ExportPreview)
def export_preview(
    request: Request,
    month: str | None = None,
    company_entity: str | None = None,
    admin=Depends(require_admin),
) -> ExportPreview:
    query, params = _ledger_query(month, company_entity, None, None, None, None, "matched")
    pending_query, pending_params = _ledger_query(month, company_entity, None, None, None, None, "pending")
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
    company_entity: str | None = None,
    admin=Depends(require_admin),
) -> StreamingResponse:
    query, params = _ledger_query(month, company_entity, None, None, None, None, "matched")
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
    filename = f"expense-ledger-{month or 'all'}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export-package.zip")
def export_package(
    request: Request,
    month: str | None = None,
    company_entity: str | None = None,
    admin=Depends(require_admin),
) -> StreamingResponse:
    with request.app.state.db.connect() as connection:
        output, filename = build_export_package(connection, month, company_entity)
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
    with request.app.state.db.connect() as connection:
        existing = connection.execute("SELECT id FROM users WHERE username = ?", (payload.username.strip(),)).fetchone()
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户名已存在")
        cursor = connection.execute(
            """
            INSERT INTO users (username, password_hash, role, employee_name, company_entity, is_active)
            VALUES (?, ?, ?, ?, ?, 1)
            """,
            (
                payload.username.strip(),
                hash_password(payload.password),
                payload.role,
                payload.employee_name.strip(),
                company_entity,
            ),
        )
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
            connection.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = ?", params)
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
