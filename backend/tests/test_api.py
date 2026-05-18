from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def make_client(tmp_path: Path, monkeypatch) -> TestClient:
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "data" / "uploads"))
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("SEED_DEMO_USERS", "true")
    monkeypatch.setenv("TENCENT_SECRET_ID", "")
    monkeypatch.setenv("TENCENT_SECRET_KEY", "")
    main = importlib.import_module("app.main")
    app = main.create_app()
    app.state.db.init(app.state.settings.seed_demo_users)
    return TestClient(app)


def auth_headers(client: TestClient, username: str, password: str) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def upload_file(client: TestClient, headers: dict[str, str], filename: str, content: bytes):
    return client.post(
        "/api/attachments",
        headers=headers,
        files={"file": (filename, content, "application/pdf")},
    )


def insert_ocr_attachment(client: TestClient, user_id: int, invoice_items: list[dict], filename: str = "ocr.pdf") -> int:
    with client.app.state.db.connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO attachments (
                user_id, original_filename, stored_path, file_hash, file_size,
                duplicate_count, ocr_status, ocr_result
            )
            VALUES (?, ?, ?, ?, ?, 0, 'success', ?)
            """,
            (
                user_id,
                filename,
                str(client.app.state.settings.upload_dir / filename),
                f"hash-{filename}",
                100,
                json.dumps({"invoice_items": invoice_items}, ensure_ascii=False),
            ),
        )
        return int(cursor.lastrowid)


def test_employee_can_create_expense_and_only_see_own_records(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    alice = auth_headers(client, "alice", "alice123")
    bob = auth_headers(client, "bob", "bob123")

    upload = upload_file(client, alice, "invoice.pdf", b"invoice-one")
    assert upload.status_code == 200

    create = client.post(
        "/api/expenses",
        headers=alice,
        json={
            "category": "差旅交通",
            "expense_month": "2026-05",
            "actual_amount": 128.5,
            "invoice_amount": 128.5,
            "is_substitute": False,
            "substitute_reason": "",
            "note": "机场快线",
            "attachment_ids": [upload.json()["id"]],
        },
    )
    assert create.status_code == 200
    assert create.json()["company_entity"] == "上海示例科技有限公司"

    alice_records = client.get("/api/expenses", headers=alice)
    bob_records = client.get("/api/expenses", headers=bob)
    assert len(alice_records.json()) == 1
    assert bob_records.json() == []


def test_substitute_and_amount_mismatch_require_reason(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    alice = auth_headers(client, "alice", "alice123")

    response = client.post(
        "/api/expenses",
        headers=alice,
        json={
            "category": "其他",
            "expense_month": "2026-05",
            "actual_amount": 100,
            "invoice_amount": 120,
            "is_substitute": True,
            "substitute_reason": "",
            "note": "",
            "attachment_ids": [],
        },
    )
    assert response.status_code == 400
    assert "说明" in response.json()["detail"]


def test_duplicate_upload_is_marked_but_not_blocked(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    alice = auth_headers(client, "alice", "alice123")

    first = upload_file(client, alice, "a.pdf", b"same-content")
    second = upload_file(client, alice, "b.pdf", b"same-content")
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["is_duplicate"] is False
    assert second.json()["is_duplicate"] is True

    create = client.post(
        "/api/expenses",
        headers=alice,
        json={
            "category": "办公采购",
            "expense_month": "2026-05",
            "actual_amount": 50,
            "invoice_amount": 50,
            "is_substitute": False,
            "substitute_reason": "",
            "note": "",
            "attachment_ids": [second.json()["id"]],
        },
    )
    assert create.status_code == 200
    assert create.json()["has_duplicate"] is True


def test_admin_can_filter_ledger_and_preview_export(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    alice = auth_headers(client, "alice", "alice123")
    admin = auth_headers(client, "admin", "admin123")

    create = client.post(
        "/api/expenses",
        headers=alice,
        json={
            "category": "市场活动",
            "expense_month": "2026-05",
            "actual_amount": 300,
            "invoice_amount": 300,
            "is_substitute": False,
            "substitute_reason": "",
            "note": "",
            "attachment_ids": [],
        },
    )
    assert create.status_code == 200

    ledger = client.get("/api/admin/ledger?month=2026-05&employee=Alice", headers=admin)
    assert ledger.status_code == 200
    assert len(ledger.json()) == 1
    assert ledger.json()[0]["employee_name"] == "Alice Chen"

    preview = client.get("/api/admin/export/preview?month=2026-05", headers=admin)
    assert preview.status_code == 200
    assert preview.json() == {"employee_count": 1, "record_count": 1, "total_amount": 300.0}

    export = client.get("/api/admin/export.xlsx?month=2026-05", headers=admin)
    assert export.status_code == 200
    assert export.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


def test_batch_upload_accepts_multiple_files(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    alice = auth_headers(client, "alice", "alice123")

    response = client.post(
        "/api/attachments/batch",
        headers=alice,
        files=[
            ("files", ("invoice-a.pdf", b"invoice-a", "application/pdf")),
            ("files", ("invoice-b.pdf", b"invoice-b", "application/pdf")),
        ],
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0]["ocr_status"] == "not_configured"
    assert body[1]["ocr_status"] == "not_configured"


def test_batch_expense_creates_one_record_per_invoice_item(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    alice = auth_headers(client, "alice", "alice123")
    attachment_id = insert_ocr_attachment(
        client,
        user_id=2,
        invoice_items=[
            {
                "buyer": "上海示例科技有限公司",
                "amount": 88.6,
                "invoice_number": "NO-1",
                "date": "2026-05-18",
                "sub_type_description": "电子普通发票",
            },
            {
                "buyer": "上海示例科技有限公司",
                "amount": 12.3,
                "invoice_number": "NO-2",
                "date": "2026-05-18",
                "sub_type_description": "出租车票",
            },
        ],
    )

    response = client.post(
        "/api/expenses/batch",
        headers=alice,
        json={
            "items": [
                {
                    "attachment_id": attachment_id,
                    "invoice_item_index": 0,
                    "category": "办公采购",
                    "expense_month": "2026-05",
                    "actual_amount": None,
                    "is_substitute": False,
                    "substitute_reason": "",
                    "note": "",
                },
                {
                    "attachment_id": attachment_id,
                    "invoice_item_index": 1,
                    "category": "差旅交通",
                    "expense_month": "2026-05",
                    "actual_amount": None,
                    "is_substitute": False,
                    "substitute_reason": "",
                    "note": "",
                },
            ]
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0]["invoice_amount"] == 88.6
    assert body[0]["actual_amount"] == 88.6
    assert body[1]["invoice_number"] == "NO-2"


def test_batch_expense_rejects_wrong_company_title(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    alice = auth_headers(client, "alice", "alice123")
    attachment_id = insert_ocr_attachment(
        client,
        user_id=2,
        invoice_items=[{"buyer": "别的公司有限公司", "amount": 88.6}],
        filename="wrong-title.pdf",
    )

    response = client.post(
        "/api/expenses/batch",
        headers=alice,
        json={
            "items": [
                {
                    "attachment_id": attachment_id,
                    "invoice_item_index": 0,
                    "category": "其他",
                    "expense_month": "2026-05",
                    "actual_amount": None,
                    "is_substitute": False,
                    "substitute_reason": "",
                    "note": "",
                }
            ]
        },
    )

    assert response.status_code == 400
    assert "抬头" in response.json()["detail"]


def test_admin_can_create_update_and_deactivate_user(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    admin = auth_headers(client, "admin", "admin123")

    create = client.post(
        "/api/admin/users",
        headers=admin,
        json={
            "username": "carol",
            "password": "carol123",
            "role": "employee",
            "employee_name": "Carol Wang",
            "company_entity": "北京示例科技有限公司",
        },
    )
    assert create.status_code == 200
    user_id = create.json()["id"]

    update = client.patch(
        f"/api/admin/users/{user_id}",
        headers=admin,
        json={"company_entity": "深圳示例科技有限公司", "password": "newpass123"},
    )
    assert update.status_code == 200
    assert update.json()["company_entity"] == "深圳示例科技有限公司"

    carol = auth_headers(client, "carol", "newpass123")
    assert client.get("/api/me", headers=carol).status_code == 200

    deactivate = client.delete(f"/api/admin/users/{user_id}", headers=admin)
    assert deactivate.status_code == 200
    assert deactivate.json()["is_active"] is False
    disabled_login = client.post("/api/auth/login", json={"username": "carol", "password": "newpass123"})
    assert disabled_login.status_code == 403
