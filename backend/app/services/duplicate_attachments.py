from __future__ import annotations

from app.schemas import DuplicateInfo


def find_duplicate_sources(connection, file_hash: str, exclude_id: int) -> list[DuplicateInfo]:
    rows = connection.execute(
        """
        SELECT a.id, a.original_filename, u.employee_name
        FROM attachments a
        JOIN users u ON u.id = a.user_id
        WHERE a.file_hash = ? AND a.id != ? AND a.id < ?
        ORDER BY a.id
        """,
        (file_hash, exclude_id, exclude_id),
    ).fetchall()
    return [
        DuplicateInfo(
            attachment_id=row["id"],
            filename=row["original_filename"],
            employee_name=row["employee_name"],
        )
        for row in rows
    ]
