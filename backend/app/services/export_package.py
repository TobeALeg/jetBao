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
    metrics = _overview_metrics(bundles)
    sheet.merge_cells("A1:G2")
    sheet["A1"] = f"{month_label(month)}发票/报销整理总览"
    sheet["A4"] = "本次报销金额合计"
    sheet["A5"] = metrics["actual_total"]
    sheet["C4"] = "票面金额合计"
    sheet["C5"] = metrics["invoice_total"]
    sheet["E4"] = "涉及人员"
    sheet["E5"] = metrics["employee_count"]
    sheet["G4"] = "发票张数"
    sheet["G5"] = metrics["invoice_count"]

    company_start = 7
    company_rows = _overview_company_rows(bundles)
    _append_overview_table(
        sheet,
        company_start,
        ["公司主体", "人员数", "报销项数", "发票张数", "票面金额合计", "本次报销金额", "票面-报销差异"],
        company_rows,
    )

    detail_start = company_start + max(len(company_rows), 1) + 3
    _append_overview_table(
        sheet,
        detail_start,
        ["公司主体", "人员", "报销项数", "发票张数", "票面金额合计", "本次报销金额", "票面-报销差异"],
        _overview_employee_rows(bundles),
    )

    note_start = detail_start + max(len(_overview_employee_rows(bundles)), 1) + 3
    sheet.merge_cells(start_row=note_start, start_column=1, end_row=note_start, end_column=7)
    sheet.cell(row=note_start, column=1, value="核对提示")
    for index, note in enumerate(_overview_notes(bundles), start=1):
        row = note_start + index
        sheet.cell(row=row, column=1, value=index)
        sheet.cell(row=row, column=2, value=note)
        sheet.merge_cells(start_row=row, start_column=2, end_row=row, end_column=7)


def _append_overview_table(sheet, start_row: int, headers: list[str], rows: list[list[object]]) -> None:
    for column, header in enumerate(headers, start=1):
        sheet.cell(row=start_row, column=column, value=header)
    if not rows:
        sheet.cell(row=start_row + 1, column=1, value="无数据")
        sheet.merge_cells(start_row=start_row + 1, start_column=1, end_row=start_row + 1, end_column=len(headers))
        return
    for row_offset, row_values in enumerate(rows, start=1):
        for column, value in enumerate(row_values, start=1):
            sheet.cell(row=start_row + row_offset, column=column, value=value)


def _overview_metrics(bundles: list[ExportBundle]) -> dict[str, float | int]:
    actual_total = round(sum(_actual_total(bundle) for bundle in bundles), 2)
    invoice_total = round(sum(_invoice_total(bundle) for bundle in bundles), 2)
    return {
        "actual_total": actual_total,
        "invoice_total": invoice_total,
        "employee_count": len({(bundle.expense["company_entity"], bundle.expense["employee_name"]) for bundle in bundles}),
        "invoice_count": sum(len(bundle.invoices) for bundle in bundles),
    }


def _overview_company_rows(bundles: list[ExportBundle]) -> list[list[object]]:
    rows = []
    for company, group in _group_bundles(bundles, lambda bundle: bundle.expense["company_entity"]).items():
        rows.append(_overview_row(company_alias(company), group))
    return rows


def _overview_employee_rows(bundles: list[ExportBundle]) -> list[list[object]]:
    rows = []
    grouped = _group_bundles(
        bundles,
        lambda bundle: (bundle.expense["company_entity"], bundle.expense["employee_name"]),
    )
    for (company, employee_name), group in grouped.items():
        rows.append(_overview_row(company_alias(company), group, employee_name))
    return rows


def _overview_row(company_name: str, bundles: list[ExportBundle], employee_name: str | None = None) -> list[object]:
    actual_total = round(sum(_actual_total(bundle) for bundle in bundles), 2)
    invoice_total = round(sum(_invoice_total(bundle) for bundle in bundles), 2)
    common = [
        company_name,
        len({bundle.expense["employee_name"] for bundle in bundles}) if employee_name is None else employee_name,
        len(bundles),
        sum(len(bundle.invoices) for bundle in bundles),
        invoice_total,
        actual_total,
        round(invoice_total - actual_total, 2),
    ]
    return common


def _group_bundles(bundles: list[ExportBundle], key_fn) -> dict:
    grouped = {}
    for bundle in bundles:
        key = key_fn(bundle)
        grouped.setdefault(key, []).append(bundle)
    return dict(sorted(grouped.items(), key=lambda item: str(item[0])))


def _actual_total(bundle: ExportBundle) -> float:
    return round(float(bundle.expense["actual_amount"]), 2)


def _overview_notes(bundles: list[ExportBundle]) -> list[str]:
    substitute_count = sum(1 for bundle in bundles if bundle.expense["is_substitute"])
    missing_documents = [
        document
        for bundle in bundles
        for document in [*bundle.transaction_attachments, *[invoice.document for invoice in bundle.invoices]]
        if not document.exists
    ]
    notes = [
        "“本次报销金额”按花费项目实际金额归集；替票场景不直接按发票票面金额报销。",
        "发票开票日期和报销归属按已提交记录整理，待补材料不会进入正式导出。",
        "“附件与待核对”列出交易记录、支付截图、详情截图等非正式发票材料。",
    ]
    if substitute_count:
        notes.append(f"共有 {substitute_count} 个替票/金额差异项，请在报销项汇总和发票明细中核对说明。")
    if missing_documents:
        notes.append(f"共有 {len(missing_documents)} 个源附件文件缺失，请在附件与待核对中补齐。")
    return notes


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
    if sheet.title == "总览":
        _style_overview_sheet(sheet)
        return

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


def _style_overview_sheet(sheet) -> None:
    navy = "1F4E78"
    pale_blue = "BFE8F4"
    pale_header = "F3F7FB"
    line_blue = "2BAAE2"
    red = "FF0000"
    border_side = Side(style="thin", color=line_blue)
    light_side = Side(style="thin", color="E5E7EB")
    currency_format = '"¥"#,##0.00;[Red]-"¥"#,##0.00'

    sheet.sheet_view.showGridLines = True
    sheet.freeze_panes = "A7"
    widths = {"A": 18, "B": 18, "C": 14, "D": 14, "E": 18, "F": 18, "G": 18}
    for column, width in widths.items():
        sheet.column_dimensions[column].width = width

    for row in sheet.iter_rows(min_row=1, max_row=sheet.max_row, min_col=1, max_col=7):
        for cell in row:
            cell.alignment = Alignment(vertical="center", wrap_text=True)
            cell.border = Border(left=light_side, right=light_side, top=light_side, bottom=light_side)
            if isinstance(cell.value, (int, float)):
                cell.number_format = "#,##0"

    title = sheet["A1"]
    title.fill = PatternFill("solid", fgColor=navy)
    title.font = Font(color="FFFFFF", bold=True, size=18)
    title.alignment = Alignment(horizontal="center", vertical="center")
    for row in range(1, 3):
        sheet.row_dimensions[row].height = 28
        for column in range(1, 8):
            sheet.cell(row=row, column=column).fill = PatternFill("solid", fgColor=navy)

    for label_cell, value_cell in (("A4", "A5"), ("C4", "C5"), ("E4", "E5"), ("G4", "G5")):
        sheet[label_cell].fill = PatternFill("solid", fgColor=pale_header)
        sheet[label_cell].font = Font(color=navy, bold=True, size=12)
        sheet[label_cell].alignment = Alignment(horizontal="center")
        sheet[value_cell].font = Font(color=navy, bold=True, size=15)
        sheet[value_cell].alignment = Alignment(horizontal="center")
    sheet["A5"].number_format = currency_format
    sheet["C5"].number_format = currency_format

    for row_index in range(1, sheet.max_row + 1):
        first_value = sheet.cell(row=row_index, column=1).value
        if first_value == "公司主体":
            for column in range(1, 8):
                cell = sheet.cell(row=row_index, column=column)
                cell.fill = PatternFill("solid", fgColor=navy)
                cell.font = Font(color=red if column == 6 else "FFFFFF", bold=True, size=12)
                cell.alignment = Alignment(horizontal="center", vertical="center")
                cell.border = Border(left=border_side, right=border_side, top=border_side, bottom=border_side)
            _style_overview_table_body(sheet, row_index + 1, currency_format, pale_blue, line_blue, red)
        if first_value == "核对提示":
            for column in range(1, 8):
                cell = sheet.cell(row=row_index, column=column)
                cell.fill = PatternFill("solid", fgColor=navy)
                cell.font = Font(color="FFFFFF", bold=True, size=12)
                cell.alignment = Alignment(horizontal="center")


def _style_overview_table_body(sheet, start_row: int, currency_format: str, fill_color: str, line_color: str, red: str) -> None:
    side = Side(style="thin", color=line_color)
    row = start_row
    while row <= sheet.max_row and sheet.cell(row=row, column=1).value not in (None, "核对提示", "公司主体"):
        use_fill = row == start_row or row % 2 == 1
        for column in range(1, 8):
            cell = sheet.cell(row=row, column=column)
            if use_fill:
                cell.fill = PatternFill("solid", fgColor=fill_color)
            cell.border = Border(left=side, right=side, top=side, bottom=side)
            if column in (5, 6, 7) and isinstance(cell.value, (int, float)):
                cell.number_format = currency_format
            if column == 6:
                cell.font = Font(color=red)
            cell.alignment = Alignment(horizontal="right" if column >= 2 else "left", vertical="center")
        row += 1
