from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json

from app.services.ocr import OcrService, OcrServiceConfig, extract_invoice_amount, normalize_invoice_item


class FakeTencentResponse:
    def __init__(self, body: dict):
        self.body = body

    def to_json_string(self) -> str:
        return json.dumps(self.body, ensure_ascii=False)


class FakeTencentClient:
    def __init__(self):
        self.request = None

    def RecognizeGeneralInvoice(self, request):
        self.request = request
        return FakeTencentResponse(
            {
                "MixedInvoiceItems": [
                    {
                        "Code": "OK",
                        "TypeDescription": "增值税发票",
                        "SubTypeDescription": "电子普通发票",
                        "Page": 1,
                        "SingleInvoiceInfos": {
                            "VatInvoice": {
                                "Title": "电子普通发票",
                                "Number": "12345678",
                                "Date": "2026-05-18",
                                "Seller": "测试商户",
                                "Total": "88.60",
                            }
                        },
                    }
                ],
                "TotalPDFCount": 2,
                "RequestId": "request-id",
            }
        )


def test_extract_invoice_amount_prefers_total_hint():
    lines = ["项目 金额 15.00", "价税合计(小写) ¥128.50", "校验码 123456"]
    assert extract_invoice_amount(lines) == 128.5


def test_ocr_returns_manual_path_when_tencent_keys_missing(tmp_path):
    file_path = tmp_path / "invoice.txt"
    file_path.write_text("invoice", encoding="utf-8")
    config = OcrServiceConfig(
        secret_id="",
        secret_key="",
        region="ap-guangzhou",
        endpoint="ocr.tencentcloudapi.com",
        action="RecognizeGeneralInvoice",
        pdf_page=1,
        enable_multiple_page=True,
    )

    status, result = OcrService(config).recognize(file_path)

    assert status == "not_configured"
    assert result["provider"] == "tencent"
    assert "手动填写" in result["message"]


def test_recognize_general_invoice_uses_pdf_multi_page_params(tmp_path):
    file_path = tmp_path / "invoices.pdf"
    file_path.write_bytes(b"%PDF fake")
    client = FakeTencentClient()
    config = OcrServiceConfig(
        secret_id="secret-id",
        secret_key="secret-key",
        region="ap-guangzhou",
        endpoint="ocr.tencentcloudapi.com",
        action="RecognizeGeneralInvoice",
        pdf_page=1,
        enable_multiple_page=True,
    )

    status, result = OcrService(config, client=client).recognize(file_path)

    assert status == "success"
    assert client.request._EnablePdf is True
    assert client.request._EnableMultiplePage is True
    assert client.request._EnableOther is True
    assert client.request._PdfPageNumber is None
    assert result["total_pdf_count"] == 2
    assert result["suggested_invoice_amount"] == 88.6
    assert result["invoice_items"][0]["invoice_number"] == "12345678"


def test_normalize_invoice_item_extracts_common_fields():
    item = {
        "TypeDescription": "火车票",
        "Page": 3,
        "SingleInvoiceInfos": {
            "TrainTicket": {
                "Title": "铁路电子客票",
                "Number": "E123",
                "DateGetOn": "2026-05-18",
                "StationGetOn": "上海",
                "Total": "45.50",
            }
        },
    }

    normalized = normalize_invoice_item(item)

    assert normalized["page"] == 3
    assert normalized["title"] == "铁路电子客票"
    assert normalized["invoice_number"] == "E123"
    assert normalized["date"] == "2026-05-18"
    assert normalized["amount"] == 45.5
