export type Role = "employee" | "admin";

export type ViewKey = "my-expenses" | "new-expense" | "admin-ledger" | "admin-users" | "export";

export type WorkspaceMode = "personal" | "admin";

export type ExpenseStatus = "draft" | "submitted";

export interface User {
  id: number;
  username: string;
  role: Role;
  employee_name: string;
  company_entity: string;
  is_active: boolean;
}

export interface Attachment {
  id: number;
  original_filename: string;
  file_hash: string;
  file_size: number;
  duplicate_count: number;
  is_duplicate: boolean;
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
  allocated_amount: number;
  remaining_amount: number;
  allocation_count: number;
  created_at: string;
  attachments: Attachment[];
  allocations: ExpenseAllocation[];
}

export interface DraftExpenseCreatePayload {
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
  created_at: string;
}

export interface ExpenseAllocationCreatePayload {
  expense_id: number;
  attachment_id: number;
  invoice_item_index: number;
  allocated_amount?: number;
  note: string;
}

export interface ExpenseInvoiceReferencePayload {
  attachment_id: number;
  invoice_item_index: number;
}

export interface ExpenseAllocationBatchCreatePayload {
  expense_id: number;
  invoices: ExpenseInvoiceReferencePayload[];
  note: string;
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
  created_at: string;
  attachment_names: string;
  allocation_summary: string;
}

export interface ExportPreview {
  employee_count: number;
  record_count: number;
  total_amount: number;
  pending_draft_count: number;
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
