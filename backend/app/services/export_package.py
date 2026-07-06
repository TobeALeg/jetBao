from __future__ import annotations

import json
import re
import sqlite3
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


INVALID_PATH_CHARS = re.compile(r'[\\/:*?"<>|\r\n]+')


@dataclass(frozen=True)
class ExportDocument:
    source_path: Path
    package_path: str
    original_filename: str
    exists: bool


@dataclass(frozen=True)
class ExportInvoice:
    allocation: sqlite3.Row
    invoice_item: dict[str, Any]
    document: ExportDocument


@dataclass(frozen=True)
class ExportBundle:
    expense: sqlite3.Row
    group_id: str
    expense_name: str
    folder_path: str
    invoices: list[ExportInvoice]
    transaction_attachments: list[ExportDocument]


def build_export_package(
    connection: sqlite3.Connection,
    month: str | None,
    company_entity: str | None,
) -> tuple[BytesIO, str]:
    bundles = load_export_bundles(connection, month, company_entity)
    workbook = build_export_workbook(bundles, month, company_entity)

    month_name = month_label(month)
    output = BytesIO()
    written_files: set[str] = set()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{month_name}报销明细.xlsx", workbook.getvalue())
        for bundle in bundles:
            for document in [*bundle.transaction_attachments, *[invoice.document for invoice in bundle.invoices]]:
                if not document.exists or document.package_path in written_files:
                    continue
                archive.write(document.source_path, document.package_path)
                written_files.add(document.package_path)

    output.seek(0)
    return output, f"{month_name}报销明细包.zip"


def build_export_workbook(
    bundles: list[ExportBundle],
    month: str | None,
    company_entity: str | None,
) -> BytesIO:
    workbook = Workbook()
    overview = workbook.active
    overview.title = "总览"
    summary = workbook.create_sheet("报销项汇总")
    invoices_sheet = workbook.create_sheet("发票明细")
    attachments_sheet = workbook.create_sheet("附件与待核对")

    _fill_overview(overview, bundles, month, company_entity)
    _fill_summary(summary, bundles)
    _fill_invoices(invoices_sheet, bundles)
    _fill_attachments(attachments_sheet, bundles)

    for sheet in workbook.worksheets:
        _style_sheet(sheet)

    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return output


def load_export_bundles(
    connection: sqlite3.Connection,
    month: str | None,
    company_entity: str | None,
) -> list[ExportBundle]:
    expenses = _fetch_submitted_expenses(connection, month, company_entity)
    month_name = month_label(month)
    used_paths: set[str] = set()
    invoice_paths_by_attachment: dict[tuple[int, int], str] = {}
    bundles: list[ExportBundle] = []

    for index, expense in enumerate(expenses, start=1):
        group_id = f"G{index:03d}"
        expense_name = _expense_name(expense)
        company_folder = f"{company_alias(expense['company_entity'])}{month_name}报销"
        employee_folder = f"{safe_path_part(expense['employee_name'], '未命名员工')}{month_name}报销"
        expense_folder = safe_path_part(
            f"{group_id}-{expense_name}-{format_amount(expense['actual_amount'])}元",
            group_id,
        )
        folder_path = f"{month_name}报销/{company_folder}/{employee_folder}/{expense_folder}"

        transactions = [
            _document_for_attachment(row, f"{folder_path}/交易记录", "交易记录", used_paths)
            for row in _fetch_transaction_attachments(connection, expense["id"])
        ]

        invoices: list[ExportInvoice] = []
        for allocation in _fetch_invoice_allocations(connection, expense["id"]):
            attachment_key = (expense["id"], allocation["attachment_id"])
            if attachment_key in invoice_paths_by_attachment:
                package_path = invoice_paths_by_attachment[attachment_key]
            else:
                prefix = allocation["invoice_number"] or f"发票-{allocation['attachment_id']}"
                package_path = _package_file_path(
                    folder=f"{folder_path}/发票",
                    prefix=prefix,
                    original_filename=allocation["original_filename"],
                    used_paths=used_paths,
                )
                invoice_paths_by_attachment[attachment_key] = package_path

            document = ExportDocument(
                source_path=Path(allocation["stored_path"]),
                package_path=package_path,
                original_filename=allocation["original_filename"],
                exists=Path(allocation["stored_path"]).exists(),
            )
            invoices.append(
                ExportInvoice(
                    allocation=allocation,
                    invoice_item=_invoice_item_from_allocation(allocation),
                    document=document,
                )
            )

        bundles.append(
            ExportBundle(
                expense=expense,
                group_id=group_id,
                expense_name=expense_name,
                folder_path=folder_path,
                invoices=invoices,
                transaction_attachments=transactions,
            )
        )
    return bundles


def month_label(month: str | None) -> str:
    if month and re.fullmatch(r"\d{4}-\d{2}", month):
        return f"{int(month[-2:])}月"
    return "全部"


def company_alias(company_entity: str) -> str:
    for keyword in ("信息科技", "企业服务"):
        if keyword in company_entity:
            return keyword
    cleaned = re.sub(r"（.*?）|\(.*?\)|有限公司|有限责任公司|上海|山途远智", "", company_entity)
    return safe_path_part(cleaned, "公司")


def safe_path_part(value: str | None, fallback: str) -> str:
    cleaned = INVALID_PATH_CHARS.sub("_", (value or "").strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ._")
    return cleaned[:80] or fallback


def format_amount(value: float | int | str | None) -> str:
    number = round(float(value or 0), 2)
    if number.is_integer():
        return str(int(number))
    return f"{number:.2f}".rstrip("0").rstrip(".")


def _fetch_submitted_expenses(
    connection: sqlite3.Connection,
    month: str | None,
    company_entity: str | None,
) -> list[sqlite3.Row]:
    where = ["expenses.status = 'submitted'"]
    params: list[object] = []
    if month:
        where.append("expenses.expense_month = ?")
        params.append(month)
    if company_entity:
        where.append("expenses.company_entity = ?")
        params.append(company_entity)

    return connection.execute(
        f"""
        SELECT expenses.*, users.employee_name
        FROM expenses
        JOIN users ON users.id = expenses.user_id
        WHERE {" AND ".join(where)}
        ORDER BY expenses.company_entity, users.employee_name, expenses.created_at, expenses.id
        """,
        params,
    ).fetchall()


def _fetch_transaction_attachments(connection: sqlite3.Connection, expense_id: int) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT attachments.*
        FROM attachments
        JOIN expense_attachments ON expense_attachments.attachment_id = attachments.id
        WHERE expense_attachments.expense_id = ?
        UNION
        SELECT * FROM attachments WHERE expense_id = ?
        ORDER BY created_at, id
        """,
        (expense_id, expense_id),
    ).fetchall()


def _fetch_invoice_allocations(connection: sqlite3.Connection, expense_id: int) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT
            expense_invoice_allocations.*,
            attachments.original_filename,
            attachments.stored_path,
            attachments.ocr_result
        FROM expense_invoice_allocations
        JOIN attachments ON attachments.id = expense_invoice_allocations.attachment_id
        WHERE expense_invoice_allocations.expense_id = ?
        ORDER BY expense_invoice_allocations.id
        """,
        (expense_id,),
    ).fetchall()


def _invoice_item_from_allocation(allocation: sqlite3.Row) -> dict[str, Any]:
    try:
        result = json.loads(allocation["ocr_result"] or "{}")
    except json.JSONDecodeError:
        return {}
    items = result.get("invoice_items")
    index = int(allocation["invoice_item_index"])
    if not isinstance(items, list) or index >= len(items) or not isinstance(items[index], dict):
        return {}
    return items[index]


def _document_for_attachment(
    attachment: sqlite3.Row,
    folder: str,
    prefix: str,
    used_paths: set[str],
) -> ExportDocument:
    return ExportDocument(
        source_path=Path(attachment["stored_path"]),
        package_path=_package_file_path(folder, prefix, attachment["original_filename"], used_paths),
        original_filename=attachment["original_filename"],
        exists=Path(attachment["stored_path"]).exists(),
    )


def _package_file_path(folder: str, prefix: str, original_filename: str, used_paths: set[str]) -> str:
    filename = safe_path_part(original_filename, "附件")
    safe_prefix = safe_path_part(prefix, "附件")
    path = f"{folder}/{safe_prefix}-{filename}"
    path = path.replace("//", "/")
    if path not in used_paths:
        used_paths.add(path)
        return path

    stem = Path(filename).stem
    suffix = Path(filename).suffix
    counter = 2
    while True:
        candidate = f"{folder}/{safe_prefix}-{stem} ({counter}){suffix}"
        if candidate not in used_paths:
            used_paths.add(candidate)
            return candidate
        counter += 1


def _expense_name(expense: sqlite3.Row) -> str:
    return (
        str(expense["project_name"] or "").strip()
        or str(expense["note"] or "").strip()
        or str(expense["category"] or "").strip()
        or "报销项"
    )


def _invoice_text(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _invoice_total(bundle: ExportBundle) -> float:
    return round(sum(float(invoice.allocation["invoice_amount"]) for invoice in bundle.invoices), 2)


def _attachment_count(bundle: ExportBundle) -> int:
    invoice_files = {invoice.document.package_path for invoice in bundle.invoices}
    return len(bundle.transaction_attachments) + len(invoice_files)


def _fill_overview(sheet, bundles: list[ExportBundle], month: str | None, company_entity: str | None) -> None:
    employee_count = len({bundle.expense["employee_name"] for bundle in bundles})
    total_amount = round(sum(float(bundle.expense["actual_amount"]) for bundle in bundles), 2)
    invoice_total = round(sum(_invoice_total(bundle) for bundle in bundles), 2)
    substitute_count = sum(1 for bundle in bundles if bundle.expense["is_substitute"])
    missing_count = sum(
        1
        for bundle in bundles
        for document in [*bundle.transaction_attachments, *[invoice.document for invoice in bundle.invoices]]
        if not document.exists
    )

    sheet.append(["导出范围", ""])
    sheet.append(["月份", month or "全部月份"])
    sheet.append(["公司主体", company_entity or "全部公司"])
    sheet.append([])
    sheet.append(["指标", "数值"])
    sheet.append(["报销人数", employee_count])
    sheet.append(["报销项数", len(bundles)])
    sheet.append(["报销金额合计", total_amount])
    sheet.append(["票面金额合计", invoice_total])
    sheet.append(["票面-报销差异", round(invoice_total - total_amount, 2)])
    sheet.append(["替票/金额差异项", substitute_count])
    sheet.append(["附件文件缺失", missing_count])


def _fill_summary(sheet, bundles: list[ExportBundle]) -> None:
    sheet.append(
        [
            "组ID",
            "公司主体",
            "购买方名称",
            "人员",
            "报销项",
            "票据状态",
            "发票张数",
            "票面金额合计",
            "本次报销金额",
            "票面-报销差异",
            "附件数",
            "备注",
        ]
    )
    for bundle in bundles:
        invoice_total = _invoice_total(bundle)
        actual_amount = round(float(bundle.expense["actual_amount"]), 2)
        sheet.append(
            [
                bundle.group_id,
                bundle.expense["company_entity"],
                bundle.expense["invoice_buyer"],
                bundle.expense["employee_name"],
                bundle.expense_name,
                _ticket_status(bundle),
                len(bundle.invoices),
                invoice_total,
                actual_amount,
                round(invoice_total - actual_amount, 2),
                _attachment_count(bundle),
                bundle.expense["substitute_reason"] or bundle.expense["note"],
            ]
        )


def _fill_invoices(sheet, bundles: list[ExportBundle]) -> None:
    sheet.append(
        [
            "公司主体",
            "购买方名称",
            "人员",
            "组ID",
            "对应报销项",
            "发票/票据类别",
            "发票号码",
            "开票日期",
            "销售方",
            "项目名称",
            "票面价税合计",
            "是否替票",
            "源文件路径",
            "备注",
        ]
    )
    for bundle in bundles:
        for invoice in bundle.invoices:
            allocation = invoice.allocation
            item = invoice.invoice_item
            sheet.append(
                [
                    bundle.expense["company_entity"],
                    allocation["invoice_buyer"],
                    bundle.expense["employee_name"],
                    bundle.group_id,
                    bundle.expense_name,
                    allocation["invoice_type"],
                    allocation["invoice_number"],
                    allocation["invoice_date"],
                    _invoice_text(item, "seller", "seller_name", "seller_title"),
                    _invoice_text(
                        item,
                        "item_name",
                        "goods_name",
                        "service_name",
                        "project_name",
                        "sub_type_description",
                        "type_description",
                    ),
                    allocation["invoice_amount"],
                    "是" if bundle.expense["is_substitute"] else "否",
                    invoice.document.package_path,
                    allocation["note"] or bundle.expense["substitute_reason"] or bundle.expense["note"],
                ]
            )


def _fill_attachments(sheet, bundles: list[ExportBundle]) -> None:
    sheet.append(["组ID", "公司主体", "人员", "附件类型", "文件名", "文件金额参考", "源文件路径", "说明"])
    for bundle in bundles:
        for document in bundle.transaction_attachments:
            sheet.append(
                [
                    bundle.group_id,
                    bundle.expense["company_entity"],
                    bundle.expense["employee_name"],
                    "交易记录",
                    document.original_filename,
                    bundle.expense["actual_amount"],
                    document.package_path if document.exists else str(document.source_path),
                    "文件缺失" if not document.exists else "花费项目佐证附件",
                ]
            )
        if not bundle.invoices:
            sheet.append(
                [
                    bundle.group_id,
                    bundle.expense["company_entity"],
                    bundle.expense["employee_name"],
                    "待核对",
                    "",
                    bundle.expense["actual_amount"],
                    "",
                    "该报销项没有发票匹配明细",
                ]
            )
        for invoice in bundle.invoices:
            if invoice.document.exists:
                continue
            sheet.append(
                [
                    bundle.group_id,
                    bundle.expense["company_entity"],
                    bundle.expense["employee_name"],
                    "发票文件缺失",
                    invoice.document.original_filename,
                    invoice.allocation["invoice_amount"],
                    str(invoice.document.source_path),
                    "数据库有发票记录，但源文件不存在",
                ]
            )


def _ticket_status(bundle: ExportBundle) -> str:
    invoice_total = _invoice_total(bundle)
    actual_amount = round(float(bundle.expense["actual_amount"]), 2)
    if not bundle.invoices:
        return "待核对"
    if invoice_total == actual_amount:
        return "已匹配"
    if invoice_total > actual_amount:
        return "替票/金额差异"
    return "部分匹配"


def _style_sheet(sheet) -> None:
    header_fill = PatternFill("solid", fgColor="0F766E")
    header_font = Font(color="FFFFFF", bold=True)
    thin = Side(style="thin", color="D9E2E0")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    max_row = sheet.max_row
    max_column = sheet.max_column
    if max_row == 0 or max_column == 0:
        return

    header_row = 1 if sheet.title != "总览" else 5
    if max_row >= header_row:
        for cell in sheet[header_row]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center")

    for row in sheet.iter_rows():
        for cell in row:
            cell.border = border
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            if isinstance(cell.value, (int, float)):
                cell.number_format = '#,##0.00'

    for column_index in range(1, max_column + 1):
        width = 12
        column_letter = get_column_letter(column_index)
        for cell in sheet[column_letter]:
            value = "" if cell.value is None else str(cell.value)
            width = max(width, min(len(value) + 2, 36))
        sheet.column_dimensions[column_letter].width = width

    sheet.freeze_panes = "A2" if sheet.title != "总览" else "A6"
    if sheet.title != "总览":
        sheet.auto_filter.ref = sheet.dimensions
