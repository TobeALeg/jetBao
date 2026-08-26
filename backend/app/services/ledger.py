from __future__ import annotations

from app.expense_month_filter import apply_expense_month_filter, normalize_month, normalize_month_part, normalize_year
from app.schemas import DuplicateInfo, LedgerRow
from app.services.duplicate_attachments import find_duplicate_sources


def build_ledger_query(
    *,
    month: str | None,
    company_entity: str | None,
    employee: str | None,
    category: str | None,
    is_substitute: bool | None,
    has_duplicate: bool | None,
    record_status: str | None,
    year: str | None = None,
    month_part: str | None = None,
    user_id: int | None = None,
) -> tuple[str, list[object]]:
    where = []
    params: list[object] = []
    apply_expense_month_filter(
        where,
        params,
        month=normalize_month(month),
        year=normalize_year(year),
        month_part=normalize_month_part(month_part),
    )
    if user_id is not None:
        where.append("expenses.user_id = ?")
        params.append(user_id)
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
            expenses.reject_reason,
            expenses.reviewed_at,
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


def load_ledger_duplicate_sources(connection, expense_id: int) -> list[DuplicateInfo]:
    attachments = connection.execute(
        """
        SELECT a.id, a.file_hash, a.duplicate_count
        FROM attachments a
        JOIN expense_invoice_allocations ea ON ea.attachment_id = a.id
        WHERE ea.expense_id = ?
        """,
        (expense_id,),
    ).fetchall()
    seen: dict[int, DuplicateInfo] = {}
    for attachment in attachments:
        if attachment["duplicate_count"] > 0:
            for source in find_duplicate_sources(
                connection,
                attachment["file_hash"],
                attachment["id"],
            ):
                seen.setdefault(source.attachment_id, source)
    return list(seen.values())


def serialize_ledger_row(
    row,
    duplicate_sources: list[DuplicateInfo] | None = None,
) -> LedgerRow:
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
        duplicate_of=duplicate_sources or [],
        reject_reason=row["reject_reason"],
        reviewed_at=row["reviewed_at"],
        created_at=row["created_at"],
        attachment_names=row["attachment_names"],
        allocation_summary=row["allocation_summary"],
    )
