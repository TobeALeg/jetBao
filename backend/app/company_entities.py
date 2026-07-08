from __future__ import annotations

import re
from typing import Literal


ALLOWED_COMPANY_ENTITIES = (
    "上海山途远智信息科技有限公司",
    "山途远智（上海）企业服务有限公司",
)

TITLE_NOISE = re.compile(r"[\s:：,，.。()（）\[\]【】《》<>“”\"']")


def normalize_company_title(value: str) -> str:
    value = value.replace("购买方", "").replace("付款方", "").replace("名称", "")
    return TITLE_NOISE.sub("", value)


def normalize_company_entity(value: str) -> str:
    return value.strip()


def is_allowed_company_entity(value: str) -> bool:
    return normalize_company_entity(value) in ALLOWED_COMPANY_ENTITIES


def invoice_buyer_match_status(buyer: str) -> Literal["exact", "partial", "none"]:
    recognized = normalize_company_title(buyer)
    if not recognized:
        return "none"

    allowed = [normalize_company_title(company) for company in ALLOWED_COMPANY_ENTITIES]
    if recognized in allowed:
        return "exact"
    if any(recognized in company or company in recognized for company in allowed):
        return "partial"
    return "none"
