from __future__ import annotations

import re


_MONTH_PATTERN = re.compile(r"^\d{4}-\d{2}$")
_MONTH_PART_PATTERN = re.compile(r"^\d{2}$")
_YEAR_PATTERN = re.compile(r"^\d{4}$")


def apply_expense_month_filter(
    where: list[str],
    params: list[object],
    *,
    month: str | None = None,
    year: str | None = None,
    month_part: str | None = None,
    column: str = "expenses.expense_month",
) -> None:
    if month:
        where.append(f"{column} = ?")
        params.append(month)
        return
    if year and month_part:
        where.append(f"{column} = ?")
        params.append(f"{year}-{month_part}")
        return
    if year:
        where.append(f"{column} LIKE ?")
        params.append(f"{year}-%")
        return
    if month_part:
        where.append(f"{column} LIKE ?")
        params.append(f"%-{month_part}")


def normalize_year(value: str | None) -> str | None:
    if not value or not _YEAR_PATTERN.fullmatch(value):
        return None
    return value


def normalize_month_part(value: str | None) -> str | None:
    if not value or not _MONTH_PART_PATTERN.fullmatch(value):
        return None
    month_number = int(value)
    if month_number < 1 or month_number > 12:
        return None
    return value


def normalize_month(value: str | None) -> str | None:
    if not value or not _MONTH_PATTERN.fullmatch(value):
        return None
    return value


def expense_period_label(
    month: str | None = None,
    year: str | None = None,
    month_part: str | None = None,
) -> str:
    if month:
        return month
    if year and month_part:
        return f"{year}-{month_part}"
    if year:
        return year
    if month_part:
        return f"第{int(month_part)}月"
    return "全部"
