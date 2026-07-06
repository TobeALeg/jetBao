from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable

from app.security import hash_password


class Database:
    def __init__(self, database_path: Path):
        self.database_path = database_path

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def init(self, seed_demo_users: bool) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('employee', 'admin')),
                    employee_name TEXT NOT NULL,
                    company_entity TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS expenses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    company_entity TEXT NOT NULL,
                    project_name TEXT NOT NULL DEFAULT '',
                    category TEXT NOT NULL,
                    expense_month TEXT NOT NULL,
                    actual_amount REAL NOT NULL,
                    invoice_amount REAL,
                    invoice_buyer TEXT NOT NULL DEFAULT '',
                    invoice_number TEXT NOT NULL DEFAULT '',
                    invoice_date TEXT NOT NULL DEFAULT '',
                    invoice_type TEXT NOT NULL DEFAULT '',
                    source_attachment_id INTEGER REFERENCES attachments(id),
                    source_invoice_index INTEGER,
                    is_substitute INTEGER NOT NULL DEFAULT 0,
                    substitute_reason TEXT NOT NULL DEFAULT '',
                    note TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'submitted',
                    has_duplicate INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS attachments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    expense_id INTEGER REFERENCES expenses(id) ON DELETE SET NULL,
                    original_filename TEXT NOT NULL,
                    stored_path TEXT NOT NULL,
                    file_hash TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    duplicate_count INTEGER NOT NULL DEFAULT 0,
                    ocr_status TEXT NOT NULL,
                    ocr_result TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS expense_attachments (
                    expense_id INTEGER NOT NULL REFERENCES expenses(id) ON DELETE CASCADE,
                    attachment_id INTEGER NOT NULL REFERENCES attachments(id) ON DELETE CASCADE,
                    PRIMARY KEY (expense_id, attachment_id)
                );

                CREATE TABLE IF NOT EXISTS expense_invoice_allocations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    expense_id INTEGER NOT NULL REFERENCES expenses(id) ON DELETE CASCADE,
                    attachment_id INTEGER NOT NULL REFERENCES attachments(id) ON DELETE CASCADE,
                    invoice_item_index INTEGER NOT NULL,
                    invoice_amount REAL NOT NULL,
                    allocated_amount REAL NOT NULL,
                    invoice_buyer TEXT NOT NULL DEFAULT '',
                    invoice_number TEXT NOT NULL DEFAULT '',
                    invoice_date TEXT NOT NULL DEFAULT '',
                    invoice_type TEXT NOT NULL DEFAULT '',
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(expense_id, attachment_id, invoice_item_index)
                );

                CREATE INDEX IF NOT EXISTS idx_expenses_user_id ON expenses(user_id);
                CREATE INDEX IF NOT EXISTS idx_expenses_month ON expenses(expense_month);
                CREATE INDEX IF NOT EXISTS idx_expenses_company ON expenses(company_entity);
                CREATE INDEX IF NOT EXISTS idx_attachments_hash ON attachments(file_hash);
                CREATE INDEX IF NOT EXISTS idx_allocations_expense ON expense_invoice_allocations(expense_id);
                CREATE INDEX IF NOT EXISTS idx_allocations_invoice_item ON expense_invoice_allocations(attachment_id, invoice_item_index);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_allocations_unique_invoice_item
                    ON expense_invoice_allocations(attachment_id, invoice_item_index);
                """
            )
            self._migrate(connection)
            if seed_demo_users:
                self._seed_demo_users(connection)
            self._ensure_admin_users(connection)

    def _migrate(self, connection: sqlite3.Connection) -> None:
        self._add_column_if_missing(connection, "users", "is_active", "INTEGER NOT NULL DEFAULT 1")
        for column, definition in (
            ("project_name", "TEXT NOT NULL DEFAULT ''"),
            ("invoice_buyer", "TEXT NOT NULL DEFAULT ''"),
            ("invoice_number", "TEXT NOT NULL DEFAULT ''"),
            ("invoice_date", "TEXT NOT NULL DEFAULT ''"),
            ("invoice_type", "TEXT NOT NULL DEFAULT ''"),
            ("source_attachment_id", "INTEGER REFERENCES attachments(id)"),
            ("source_invoice_index", "INTEGER"),
        ):
            self._add_column_if_missing(connection, "expenses", column, definition)
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS expense_attachments (
                expense_id INTEGER NOT NULL REFERENCES expenses(id) ON DELETE CASCADE,
                attachment_id INTEGER NOT NULL REFERENCES attachments(id) ON DELETE CASCADE,
                PRIMARY KEY (expense_id, attachment_id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS expense_invoice_allocations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                expense_id INTEGER NOT NULL REFERENCES expenses(id) ON DELETE CASCADE,
                attachment_id INTEGER NOT NULL REFERENCES attachments(id) ON DELETE CASCADE,
                invoice_item_index INTEGER NOT NULL,
                invoice_amount REAL NOT NULL,
                allocated_amount REAL NOT NULL,
                invoice_buyer TEXT NOT NULL DEFAULT '',
                invoice_number TEXT NOT NULL DEFAULT '',
                invoice_date TEXT NOT NULL DEFAULT '',
                invoice_type TEXT NOT NULL DEFAULT '',
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(expense_id, attachment_id, invoice_item_index)
            )
            """
        )
        connection.execute(
            """
            INSERT OR IGNORE INTO expense_attachments (expense_id, attachment_id)
            SELECT expense_id, id FROM attachments WHERE expense_id IS NOT NULL
            """
        )
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_expense_source_item
                ON expenses(source_attachment_id, source_invoice_index)
                WHERE source_attachment_id IS NOT NULL AND source_invoice_index IS NOT NULL
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_allocations_expense
                ON expense_invoice_allocations(expense_id)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_allocations_invoice_item
                ON expense_invoice_allocations(attachment_id, invoice_item_index)
            """
        )
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_allocations_unique_invoice_item
                ON expense_invoice_allocations(attachment_id, invoice_item_index)
            """
        )
        connection.execute(
            """
            INSERT OR IGNORE INTO expense_invoice_allocations (
                expense_id, attachment_id, invoice_item_index, invoice_amount,
                allocated_amount, invoice_buyer, invoice_number, invoice_date,
                invoice_type, note
            )
            SELECT
                id, source_attachment_id, source_invoice_index,
                COALESCE(invoice_amount, actual_amount),
                actual_amount,
                invoice_buyer,
                invoice_number,
                invoice_date,
                invoice_type,
                substitute_reason
            FROM expenses
            WHERE source_attachment_id IS NOT NULL AND source_invoice_index IS NOT NULL
            """
        )

    def _ensure_admin_users(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            UPDATE users
            SET role = 'admin'
            WHERE lower(username) IN ('dandi', 'ouyang')
               OR employee_name IN ('艾丹迪', 'Dandi', '欧阳')
            """
        )

    def _add_column_if_missing(self, connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        columns = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _seed_demo_users(self, connection: sqlite3.Connection) -> None:
        existing = connection.execute("SELECT COUNT(*) AS count FROM users").fetchone()["count"]
        if existing:
            return
        users = [
            ("admin", "admin123", "admin", "财务管理员", "上海示例科技有限公司"),
            ("alice", "alice123", "employee", "Alice Chen", "上海示例科技有限公司"),
            ("bob", "bob123", "employee", "Bob Li", "杭州示例信息有限公司"),
            ("Dandi", "dandi123", "admin", "艾丹迪", "上海山途远智信息科技有限公司"),
            ("Ouyang", "ouyang123", "admin", "欧阳", "上海山途远智信息科技有限公司"),
        ]
        connection.executemany(
            """
            INSERT INTO users (username, password_hash, role, employee_name, company_entity)
            VALUES (?, ?, ?, ?, ?)
            """,
            [(username, hash_password(password), role, name, company) for username, password, role, name, company in users],
        )


def one(connection: sqlite3.Connection, query: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
    return connection.execute(query, tuple(params)).fetchone()
