from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class UserResponse(BaseModel):
    id: int
    username: str
    role: str
    employee_name: str
    company_entity: str
    is_active: bool = True


class LoginResponse(BaseModel):
    token: str
    user: UserResponse


class AttachmentResponse(BaseModel):
    id: int
    original_filename: str
    file_hash: str
    file_size: int
    duplicate_count: int
    is_duplicate: bool
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
    created_at: str


class ExpenseAllocationCreateRequest(BaseModel):
    expense_id: int
    attachment_id: int
    invoice_item_index: int = Field(ge=0)
    allocated_amount: float | None = Field(default=None, gt=0)
    note: str = ""


class ExpenseInvoiceReference(BaseModel):
    attachment_id: int
    invoice_item_index: int = Field(ge=0)


class ExpenseAllocationBatchCreateRequest(BaseModel):
    expense_id: int
    invoices: list[ExpenseInvoiceReference] = Field(min_length=1)
    note: str = ""


class ExpenseAttachmentLinkRequest(BaseModel):
    attachment_ids: list[int] = Field(min_length=1)


class ExpenseCreateRequest(BaseModel):
    project_name: str = ""
    category: str = Field(min_length=1)
    expense_month: str = Field(pattern=r"^\d{4}-\d{2}$")
    actual_amount: float = Field(gt=0)
    invoice_amount: float | None = Field(default=None, ge=0)
    is_substitute: bool = False
    substitute_reason: str = ""
    note: str = ""
    attachment_ids: list[int] = []


class DraftExpenseCreateRequest(BaseModel):
    project_name: str = Field(min_length=1)
    actual_amount: float = Field(gt=0)
    expense_month: str = Field(pattern=r"^\d{4}-\d{2}$")
    category: str = "差旅交通"


class ExpenseItemCreateRequest(BaseModel):
    attachment_id: int
    invoice_item_index: int = Field(ge=0)
    category: str = Field(min_length=1)
    expense_month: str = Field(pattern=r"^\d{4}-\d{2}$")
    actual_amount: float | None = Field(default=None, gt=0)
    is_substitute: bool = False
    substitute_reason: str = ""
    note: str = ""


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
    status: str
    has_duplicate: bool
    allocated_amount: float = 0
    remaining_amount: float = 0
    allocation_count: int = 0
    created_at: str
    attachments: list[AttachmentResponse]
    allocations: list[ExpenseAllocationResponse] = []


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
    status: str
    has_duplicate: bool
    created_at: str
    attachment_names: str
    allocation_summary: str


class AdminUserResponse(BaseModel):
    id: int
    username: str
    role: str
    employee_name: str
    company_entity: str
    is_active: bool
    created_at: str


class AdminUserCreateRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)
    role: str = Field(pattern=r"^(employee|admin)$")
    employee_name: str = Field(min_length=1)
    company_entity: str = Field(min_length=1)


class AdminUserUpdateRequest(BaseModel):
    password: str | None = None
    role: str | None = Field(default=None, pattern=r"^(employee|admin)$")
    employee_name: str | None = None
    company_entity: str | None = None
    is_active: bool | None = None


class ExportPreview(BaseModel):
    employee_count: int
    record_count: int
    total_amount: float
    pending_draft_count: int
