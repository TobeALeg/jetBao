from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from app.config import Settings


MAX_BASE64_BYTES = 10 * 1024 * 1024
MAX_TEXT_LINES = 80
MAX_REASONABLE_AMOUNT = 1_000_000
AMOUNT_PATTERN = re.compile(r"(?:￥|¥|RMB)?\s*([0-9]+(?:,[0-9]{3})*(?:\.[0-9]{1,2})?)")
AMOUNT_HINTS = ("价税合计", "合计", "小写", "金额", "实付", "支付", "总计")


class OcrClientProtocol(Protocol):
    def RecognizeGeneralInvoice(self, request: Any) -> Any:
        ...

    def GeneralAccurateOCR(self, request: Any) -> Any:
        ...

    def GeneralBasicOCR(self, request: Any) -> Any:
        ...


@dataclass(frozen=True)
class OcrServiceConfig:
    secret_id: str
    secret_key: str
    region: str
    endpoint: str
    action: str
    pdf_page: int
    enable_multiple_page: bool

    @classmethod
    def from_settings(cls, settings: Settings) -> "OcrServiceConfig":
        return cls(
            secret_id=settings.tencent_secret_id,
            secret_key=settings.tencent_secret_key,
            region=settings.tencent_ocr_region,
            endpoint=settings.tencent_ocr_endpoint,
            action=settings.tencent_ocr_action,
            pdf_page=settings.tencent_ocr_pdf_page,
            enable_multiple_page=settings.tencent_ocr_enable_multiple_page,
        )


class OcrService:
    def __init__(self, config: OcrServiceConfig, client: OcrClientProtocol | None = None):
        self.config = config
        self.client = client

    def recognize(self, file_path: Path) -> tuple[str, dict]:
        if not self.config.secret_id or not self.config.secret_key:
            return "not_configured", {
                "provider": "tencent",
                "message": "腾讯云 OCR 未配置，可手动填写报销信息。",
                "filename": file_path.name,
            }

        file_bytes = file_path.read_bytes()
        encoded_size = len(base64.b64encode(file_bytes))
        if encoded_size > MAX_BASE64_BYTES:
            return "failed", {
                "provider": "tencent",
                "message": "附件超过腾讯云 OCR Base64 大小限制，请手动填写。",
                "filename": file_path.name,
                "encoded_size": encoded_size,
            }

        try:
            response = self._call_tencent(file_path, file_bytes)
            result = self._normalize_response(response)
            return "success", {
                "provider": "tencent",
                "action": self.config.action,
                "message": "腾讯云 OCR 识别完成，请核对后填写报销信息。",
                "filename": file_path.name,
                **result,
            }
        except Exception as exc:
            return "failed", {
                "provider": "tencent",
                "action": self.config.action,
                "message": "腾讯云 OCR 调用失败，可手动填写报销信息。",
                "filename": file_path.name,
                "error": str(exc),
            }

    def _call_tencent(self, file_path: Path, file_bytes: bytes) -> dict[str, Any]:
        client = self.client or self._build_client()
        action = self.config.action
        image_base64 = base64.b64encode(file_bytes).decode("utf-8")
        params: dict[str, Any] = {
            "ImageBase64": image_base64,
        }
        if action == "RecognizeGeneralInvoice":
            is_pdf = file_path.suffix.lower() == ".pdf"
            params.update(
                {
                    "EnablePdf": is_pdf,
                    "EnableOther": True,
                    "EnableMultiplePage": is_pdf and self.config.enable_multiple_page,
                }
            )
            if is_pdf and not self.config.enable_multiple_page:
                params["PdfPageNumber"] = self.config.pdf_page
        else:
            params.update(
                {
                    "IsPdf": file_path.suffix.lower() == ".pdf",
                    "PdfPageNumber": self.config.pdf_page,
                }
            )

        if action == "RecognizeGeneralInvoice":
            request = self._build_request("RecognizeGeneralInvoiceRequest", params)
            response = client.RecognizeGeneralInvoice(request)
        elif action == "GeneralBasicOCR":
            request = self._build_request("GeneralBasicOCRRequest", params)
            response = client.GeneralBasicOCR(request)
        elif action == "GeneralAccurateOCR":
            request = self._build_request("GeneralAccurateOCRRequest", params)
            response = client.GeneralAccurateOCR(request)
        else:
            raise ValueError("TENCENT_OCR_ACTION 只支持 RecognizeGeneralInvoice、GeneralAccurateOCR 或 GeneralBasicOCR")

        return json.loads(response.to_json_string())

    def _build_client(self) -> OcrClientProtocol:
        from tencentcloud.common import credential
        from tencentcloud.common.profile.client_profile import ClientProfile
        from tencentcloud.common.profile.http_profile import HttpProfile
        from tencentcloud.ocr.v20181119 import ocr_client

        cred = credential.Credential(self.config.secret_id, self.config.secret_key)
        http_profile = HttpProfile()
        http_profile.endpoint = self.config.endpoint
        client_profile = ClientProfile()
        client_profile.httpProfile = http_profile
        return ocr_client.OcrClient(cred, self.config.region, client_profile)

    def _build_request(self, request_class_name: str, params: dict[str, Any]) -> Any:
        from tencentcloud.ocr.v20181119 import models

        request_class = getattr(models, request_class_name)
        request = request_class()
        request.from_json_string(json.dumps(params))
        return request

    def _normalize_response(self, response: dict[str, Any]) -> dict[str, Any]:
        if self.config.action == "RecognizeGeneralInvoice":
            return self._normalize_general_invoice_response(response)

        detections = response.get("TextDetections") or []
        text_lines = [
            {
                "text": item.get("DetectedText", ""),
                "confidence": item.get("Confidence"),
            }
            for item in detections
            if item.get("DetectedText")
        ][:MAX_TEXT_LINES]
        full_text = "\n".join(line["text"] for line in text_lines)
        suggested_amount = extract_invoice_amount([line["text"] for line in text_lines])

        return {
            "request_id": response.get("RequestId", ""),
            "angle": response.get("Angle"),
            "suggested_invoice_amount": suggested_amount,
            "text_lines": text_lines,
            "full_text": full_text,
        }

    def _normalize_general_invoice_response(self, response: dict[str, Any]) -> dict[str, Any]:
        mixed_items = response.get("MixedInvoiceItems") or []
        invoice_items = [normalize_invoice_item(item) for item in mixed_items]
        suggested_amount = round(
            sum(item["amount"] for item in invoice_items if isinstance(item.get("amount"), (int, float))),
            2,
        )
        full_text = "\n".join(item["summary"] for item in invoice_items if item.get("summary"))

        return {
            "request_id": response.get("RequestId", ""),
            "total_pdf_count": response.get("TotalPDFCount"),
            "suggested_invoice_amount": suggested_amount if invoice_items else None,
            "invoice_items": invoice_items,
            "full_text": full_text,
        }


def normalize_invoice_item(item: dict[str, Any]) -> dict[str, Any]:
    invoice_type, detail = _pick_invoice_detail(item.get("SingleInvoiceInfos"))
    amount = _amount_from_invoice_detail(detail)
    title = _first_text(detail, ("Title", "FormName", "Kind"))
    code = _first_text(detail, ("Code", "InvoiceCode", "CheckCode"))
    number = _first_text(detail, ("Number", "InvoiceNumber", "ReceiptNumber", "SerialNumber"))
    date = _first_text(detail, ("Date", "DateGetOn", "DateStart"))
    seller = _first_text(detail, ("Seller", "SellerName", "CompanyName", "Place", "AgentCode"))
    buyer = _first_text(detail, ("Buyer", "BuyerName", "PurchaserName", "Payer", "UserName", "Name"))

    return {
        "code": item.get("Code", ""),
        "type": item.get("Type"),
        "sub_type": item.get("SubType", invoice_type),
        "type_description": item.get("TypeDescription", ""),
        "sub_type_description": item.get("SubTypeDescription", ""),
        "page": item.get("Page"),
        "angle": item.get("Angle"),
        "title": title,
        "invoice_code": code,
        "invoice_number": number,
        "date": date,
        "seller": seller,
        "buyer": buyer,
        "amount": amount,
        "summary": _invoice_summary(item, detail, amount),
        "raw": detail,
    }


def _pick_invoice_detail(single_infos: Any) -> tuple[str, dict[str, Any]]:
    if not isinstance(single_infos, dict):
        return "", {}
    for invoice_type, detail in single_infos.items():
        if isinstance(detail, dict) and detail:
            return invoice_type, detail
    return "", {}


def _first_text(data: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _amount_from_invoice_detail(data: dict[str, Any]) -> float | None:
    for key in ("Total", "TotalAmount", "Amount", "Fare", "Price", "SubTotal", "PretaxAmount"):
        value = data.get(key)
        amount = _parse_amount(str(value)) if value not in (None, "") else None
        if amount is not None:
            return round(amount, 2)
    return extract_invoice_amount([str(value) for value in data.values() if isinstance(value, (str, int, float))])


def _invoice_summary(item: dict[str, Any], detail: dict[str, Any], amount: float | None) -> str:
    parts = [
        str(item.get("SubTypeDescription") or item.get("TypeDescription") or ""),
        _first_text(detail, ("Title", "Kind")),
        _first_text(detail, ("Date", "DateGetOn", "DateStart")),
        str(amount) if amount is not None else "",
    ]
    return " / ".join(part for part in parts if part)


def extract_invoice_amount(lines: list[str]) -> float | None:
    candidates: list[float] = []
    hinted_candidates: list[float] = []

    for line in lines:
        normalized = line.replace("，", ",").replace("。", ".").replace(" ", "")
        for match in AMOUNT_PATTERN.finditer(normalized):
            value = _parse_amount(match.group(1))
            if value is None:
                continue
            candidates.append(value)
            if any(hint in normalized for hint in AMOUNT_HINTS):
                hinted_candidates.append(value)

    source = hinted_candidates or candidates
    if not source:
        return None
    return round(max(source), 2)


def _parse_amount(value: str) -> float | None:
    try:
        amount = float(value.replace(",", ""))
    except ValueError:
        return None
    if amount <= 0:
        return None
    if amount > MAX_REASONABLE_AMOUNT:
        return None
    return amount
