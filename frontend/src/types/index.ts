export type Role = "employee" | "admin";

export type ViewKey = "monthly" | "materials" | "history" | "admin-users";

export type WorkspaceMode = "personal" | "admin";

export type ExpenseStatus = "pending" | "matched" | "reviewed";

export interface User {
  id: number;
  username: string;
  role: Role;
  employee_name: string;
  company_entity: string;
  is_active: boolean;
}

export interface DuplicateInfo {
  attachment_id: number;
  filename: string;
  employee_name: string;
}

export interface Attachment {
  id: number;
  original_filename: string;
  file_hash: string;
  file_size: number;
  duplicate_count: number;
  is_duplicate: boolean;
  duplicate_of: DuplicateInfo[];
  pool_status: "staged" | "pooled";
  ocr_status: string;
  ocr_result: Record<string, unknown>;
  created_at: string;
  preview_url?: string;
}

export interface ExpenseAllocation {
  id: number;
  expense_id: number;
  attachment_id: number;
  invoice_item_index: number;
  invoice_amount: number;
  allocated_amount: number;
  invoice_buyer: string;
  invoice_number: string;
  invoice_date: string;
  invoice_type: string;
  note: string;
  created_at: string;
}

export interface Expense {
  id: number;
  employee_name: string;
  company_entity: string;
  project_name: string;
  category: string;
  expense_month: string;
  actual_amount: number;
  invoice_amount: number | null;
  invoice_buyer: string;
  invoice_number: string;
  invoice_date: string;
  invoice_type: string;
  is_substitute: boolean;
  substitute_reason: string;
  note: string;
  status: ExpenseStatus;
  has_duplicate: boolean;
  duplicate_of: DuplicateInfo[];
  allocated_amount: number;
  remaining_amount: number;
  allocation_count: number;
  reject_reason: string;
  reviewed_at: string;
  created_at: string;
  attachments: Attachment[];
  allocations: ExpenseAllocation[];
}

// V2: Expense submit
export interface ExpenseSubmitPayload {
  project_name: string;
  actual_amount: number;
  expense_month: string;
  category: string;
  invoices: ExpenseInvoiceReferencePayload[];
  attachment_ids: number[];
  note: string;
  buyer_confirmed?: boolean;
}

// Legacy alias
export type DraftExpenseCreatePayload = ExpenseCreatePayload;

export interface ExpenseCreatePayload {
  project_name: string;
  actual_amount: number;
  expense_month: string;
  category: string;
}

export interface ExpenseItemCreatePayload {
  attachment_id: number;
  invoice_item_index: number;
  category: string;
  expense_month: string;
  actual_amount: number | null;
  is_substitute: boolean;
  substitute_reason: string;
  note: string;
  buyer_confirmed?: boolean;
}

export interface DraftExpenseCompletePayload {
  attachment_id: number;
  invoice_item_index: number;
  category: string;
  expense_month: string;
  actual_amount: number;
  is_substitute: boolean;
  substitute_reason: string;
  note: string;
  buyer_confirmed?: boolean;
}

export interface InvoicePoolItem {
  attachment_id: number;
  attachment_name: string;
  invoice_item_index: number;
  invoice_amount: number;
  allocated_amount: number;
  remaining_amount: number;
  invoice_buyer: string;
  invoice_number: string;
  invoice_date: string;
  invoice_type: string;
  ocr_status: string;
  is_duplicate: boolean;
  duplicate_of: DuplicateInfo[];
  created_at: string;
}

export interface ExpenseAllocationCreatePayload {
  expense_id: number;
  attachment_id: number;
  invoice_item_index: number;
  allocated_amount?: number;
  note: string;
  buyer_confirmed?: boolean;
}

export interface ExpenseInvoiceReferencePayload {
  attachment_id: number;
  invoice_item_index: number;
}

export interface ExpenseAllocationBatchCreatePayload {
  expense_id: number;
  invoices: ExpenseInvoiceReferencePayload[];
  note: string;
  buyer_confirmed?: boolean;
}

export interface ExpenseAttachmentLinkPayload {
  attachment_ids: number[];
}

export interface LedgerRow {
  id: number;
  company_entity: string;
  employee_name: string;
  project_name: string;
  category: string;
  expense_month: string;
  actual_amount: number;
  invoice_amount: number | null;
  invoice_buyer: string;
  invoice_number: string;
  invoice_date: string;
  invoice_type: string;
  is_substitute: boolean;
  substitute_reason: string;
  note: string;
  status: ExpenseStatus;
  has_duplicate: boolean;
  duplicate_of: DuplicateInfo[];
  reject_reason: string;
  reviewed_at: string;
  created_at: string;
  attachment_names: string;
  allocation_summary: string;
}

export interface ExportPreview {
  employee_count: number;
  record_count: number;
  total_amount: number;
  pending_count: number;
}

export interface AdminUser {
  id: number;
  username: string;
  role: Role;
  employee_name: string;
  company_entity: string;
  is_active: boolean;
  created_at: string;
}

export interface AdminUserCreatePayload {
  username: string;
  password: string;
  role: Role;
  employee_name: string;
  company_entity: string;
}

export interface AdminUserUpdatePayload {
  password?: string;
  role?: Role;
  employee_name?: string;
  company_entity?: string;
  is_active?: boolean;
}

export interface PasswordChangePayload {
  current_password: string;
  new_password: string;
}
