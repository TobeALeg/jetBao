export type Role = "employee" | "admin";

export type ViewKey = "my-expenses" | "new-expense" | "admin-ledger" | "admin-users" | "export";

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
  ocr_status: string;
  ocr_result: Record<string, unknown>;
  created_at: string;
  preview_url?: string;
}

export interface Expense {
  id: number;
  employee_name: string;
  company_entity: string;
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
  status: string;
  has_duplicate: boolean;
  created_at: string;
  attachments: Attachment[];
}

export interface ExpenseCreatePayload {
  category: string;
  expense_month: string;
  actual_amount: number;
  invoice_amount: number | null;
  is_substitute: boolean;
  substitute_reason: string;
  note: string;
  attachment_ids: number[];
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

export interface LedgerRow {
  id: number;
  company_entity: string;
  employee_name: string;
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
  has_duplicate: boolean;
  created_at: string;
  attachment_names: string;
}

export interface ExportPreview {
  employee_count: number;
  record_count: number;
  total_amount: number;
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
