from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class UserResponse(BaseModel):
    id: int
    username: str
    email: str | None = None
    role: str
    employee_name: str
    company_entity: str
    is_active: bool = True
    guide_seen: bool = False


class LoginResponse(BaseModel):
    token: str
    user: UserResponse


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=6)


class DuplicateInfo(BaseModel):
    attachment_id: int
    filename: str
    employee_name: str


class AttachmentResponse(BaseModel):
    id: int
    original_filename: str
    file_hash: str
    file_size: int
    duplicate_count: int
    is_duplicate: bool
    duplicate_of: list[DuplicateInfo] = []
    pool_status: str
    ocr_status: str
    ocr_result: dict
    created_at: str


class ExpenseAllocationResponse(BaseModel):
    id: int
    expense_id: int
    attachment_id: int
    invoice_item_index: int
    invoice_amount: float
    allocated_amount: float
    invoice_buyer: str
    invoice_number: str
    invoice_date: str
    invoice_type: str
    note: str
    created_at: str


class InvoicePoolItem(BaseModel):
    attachment_id: int
    attachment_name: str
    invoice_item_index: int
    invoice_amount: float
    allocated_amount: float
    remaining_amount: float
    invoice_buyer: str
    invoice_number: str
    invoice_date: str
    invoice_type: str
    ocr_status: str
    is_duplicate: bool
    duplicate_of: list[DuplicateInfo] = []
    created_at: str


class ExpenseInvoiceReference(BaseModel):
    attachment_id: int
    invoice_item_index: int = Field(ge=0)


class ExpenseAllocationCreateRequest(BaseModel):
    expense_id: int
    attachment_id: int
    invoice_item_index: int = Field(ge=0)
    allocated_amount: float | None = Field(default=None, gt=0)
    note: str = ""
    buyer_confirmed: bool = False


class ExpenseAllocationBatchCreateRequest(BaseModel):
    expense_id: int
    invoices: list[ExpenseInvoiceReference] = Field(min_length=1)
    note: str = ""
    buyer_confirmed: bool = False


class ExpenseAttachmentLinkRequest(BaseModel):
    attachment_ids: list[int] = Field(min_length=1)


class AttachmentPoolRequest(BaseModel):
    attachment_ids: list[int] = Field(min_length=1)


# ── V2: Expense Create / Submit ────────────────────────────

class ExpenseCreateRequest(BaseModel):
    """创建待处理花费（原 DraftExpenseCreateRequest）"""
    project_name: str = Field(min_length=1)
    actual_amount: float = Field(gt=0)
    expense_month: str = Field(pattern=r"^\d{4}-\d{2}$")
    category: str = "差旅交通"
    is_substitute: bool = False
    substitute_reason: str = ""


class ExpenseSubmitRequest(BaseModel):
    """一次性创建花费 + 绑定发票 + 挂佐证材料 + 直接提交"""
    project_name: str = Field(min_length=1)
    actual_amount: float = Field(gt=0)
    expense_month: str = Field(pattern=r"^\d{4}-\d{2}$")
    category: str = "差旅交通"
    invoices: list[ExpenseInvoiceReference] = []
    attachment_ids: list[int] = []
    note: str = ""
    buyer_confirmed: bool = False
    is_substitute: bool = False
    substitute_reason: str = ""


class PendingExpenseSubmitRequest(BaseModel):
    """提交已有待处理花费时可同步更新替票信息"""
    is_substitute: bool | None = None
    substitute_reason: str | None = None


class ExpenseResponse(BaseModel):
    id: int
    employee_name: str
    company_entity: str
    project_name: str
    category: str
    expense_month: str
    actual_amount: float
    invoice_amount: float | None
    invoice_buyer: str
    invoice_number: str
    invoice_date: str
    invoice_type: str
    is_substitute: bool
    substitute_reason: str
    note: str
    status: str  # pending | matched | reviewed
    has_duplicate: bool
    duplicate_of: list[DuplicateInfo] = []
    allocated_amount: float = 0
    remaining_amount: float = 0
    allocation_count: int = 0
    reject_reason: str = ""
    reviewed_at: str = ""
    created_at: str
    attachments: list[AttachmentResponse]
    allocations: list[ExpenseAllocationResponse] = []
    invoice_attachments: list[AttachmentResponse] = []


class ExpenseReviewDetailResponse(ExpenseResponse):
    pass


class ExpenseBulkApproveResponse(BaseModel):
    approved_count: int


class LedgerRow(BaseModel):
    id: int
    company_entity: str
    employee_name: str
    project_name: str
    category: str
    expense_month: str
    actual_amount: float
    invoice_amount: float | None
    invoice_buyer: str
    invoice_number: str
    invoice_date: str
    invoice_type: str
    is_substitute: bool
    substitute_reason: str
    note: str
    status: str  # pending | matched | reviewed
    has_duplicate: bool
    duplicate_of: list[DuplicateInfo] = []
    reject_reason: str = ""
    reviewed_at: str = ""
    created_at: str
    attachment_names: str
    allocation_summary: str


# ── Admin ──────────────────────────────────────────────────

class AdminUserResponse(BaseModel):
    id: int
    username: str
    email: str | None = None
    identity_id: str | None = None
    role: str
    employee_name: str
    company_entity: str
    is_active: bool
    created_at: str


class AdminUserCreateRequest(BaseModel):
    username: str = Field(min_length=1)
    email: str | None = None
    password: str | None = Field(default=None, min_length=1)
    role: str = Field(pattern=r"^(employee|admin)$")
    employee_name: str = Field(min_length=1)
    company_entity: str = Field(min_length=1)


class AdminUserUpdateRequest(BaseModel):
    email: str | None = None
    password: str | None = None
    role: str | None = Field(default=None, pattern=r"^(employee|admin)$")
    employee_name: str | None = None
    company_entity: str | None = None
    is_active: bool | None = None


class ExpenseRejectRequest(BaseModel):
    reason: str = ""


class ExportPreview(BaseModel):
    employee_count: int
    record_count: int
    total_amount: float
    pending_count: int


# ── Legacy aliases (keep for migration transition) ──────────

DraftExpenseCreateRequest = ExpenseCreateRequest

# Batch create (kept for backward compat, may be removed later)
class ExpenseItemCreateRequest(BaseModel):
    attachment_id: int
    invoice_item_index: int = Field(ge=0)
    category: str = Field(min_length=1)
    expense_month: str = Field(pattern=r"^\d{4}-\d{2}$")
    actual_amount: float | None = Field(default=None, gt=0)
    is_substitute: bool = False
    substitute_reason: str = ""
    note: str = ""
    buyer_confirmed: bool = False


class ExpenseBatchCreateRequest(BaseModel):
    items: list[ExpenseItemCreateRequest] = Field(min_length=1)


class DraftExpenseCompleteRequest(BaseModel):
    attachment_id: int
    invoice_item_index: int = Field(ge=0)
    category: str = Field(min_length=1)
    expense_month: str = Field(pattern=r"^\d{4}-\d{2}$")
    actual_amount: float = Field(gt=0)
    is_substitute: bool = False
    substitute_reason: str = ""
    note: str = ""
    buyer_confirmed: bool = False
