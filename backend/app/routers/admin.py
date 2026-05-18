from __future__ import annotations

from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from openpyxl import Workbook

from app.dependencies import require_admin
from app.schemas import AdminUserCreateRequest, AdminUserResponse, AdminUserUpdateRequest, ExportPreview, LedgerRow
from app.security import hash_password


router = APIRouter(prefix="/api/admin", tags=["admin"])


def _ledger_query(
    month: str | None,
    company_entity: str | None,
    employee: str | None,
    category: str | None,
    is_substitute: bool | None,
    has_duplicate: bool | None,
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

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    query = f"""
        SELECT
            expenses.id,
            expenses.company_entity,
            users.employee_name,
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
            expenses.has_duplicate,
            expenses.created_at,
            COALESCE(GROUP_CONCAT(attachments.original_filename, '、'), '') AS attachment_names
        FROM expenses
        JOIN users ON users.id = expenses.user_id
        LEFT JOIN expense_attachments ON expense_attachments.expense_id = expenses.id
        LEFT JOIN attachments ON attachments.id = expense_attachments.attachment_id
        {where_sql}
        GROUP BY expenses.id
        ORDER BY expenses.created_at DESC
    """
    return query, params


def _serialize_ledger_row(row) -> LedgerRow:
    return LedgerRow(
        id=row["id"],
        company_entity=row["company_entity"],
        employee_name=row["employee_name"],
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
        has_duplicate=bool(row["has_duplicate"]),
        created_at=row["created_at"],
        attachment_names=row["attachment_names"],
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
    admin=Depends(require_admin),
) -> list[LedgerRow]:
    query, params = _ledger_query(month, company_entity, employee, category, is_substitute, has_duplicate)
    with request.app.state.db.connect() as connection:
        rows = connection.execute(query, params).fetchall()
    return [_serialize_ledger_row(row) for row in rows]


@router.get("/export/preview", response_model=ExportPreview)
def export_preview(
    request: Request,
    month: str | None = None,
    company_entity: str | None = None,
    admin=Depends(require_admin),
) -> ExportPreview:
    query, params = _ledger_query(month, company_entity, None, None, None, None)
    with request.app.state.db.connect() as connection:
        rows = connection.execute(query, params).fetchall()
    employee_count = len({row["employee_name"] for row in rows})
    total_amount = round(sum(float(row["actual_amount"]) for row in rows), 2)
    return ExportPreview(employee_count=employee_count, record_count=len(rows), total_amount=total_amount)


@router.get("/export.xlsx")
def export_excel(
    request: Request,
    month: str | None = None,
    company_entity: str | None = None,
    admin=Depends(require_admin),
) -> StreamingResponse:
    query, params = _ledger_query(month, company_entity, None, None, None, None)
    with request.app.state.db.connect() as connection:
        rows = connection.execute(query, params).fetchall()

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "报销台账"
    headers = [
        "公司主体",
        "员工",
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
        "附件文件名",
    ]
    sheet.append(headers)
    for row in rows:
        sheet.append(
            [
                row["company_entity"],
                row["employee_name"],
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
                payload.company_entity.strip(),
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
            params.append(payload.company_entity.strip())
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
