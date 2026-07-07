import type {
  AdminUser,
  AdminUserCreatePayload,
  AdminUserUpdatePayload,
  Attachment,
  DraftExpenseCompletePayload,
  DraftExpenseCreatePayload,
  Expense,
  ExpenseAllocationBatchCreatePayload,
  ExpenseAllocationCreatePayload,
  ExpenseAttachmentLinkPayload,
  ExpenseCreatePayload,
  ExpenseItemCreatePayload,
  ExportPreview,
  InvoicePoolItem,
  LedgerRow,
  User
} from "../types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "/api";
const TOKEN_KEY = "jetbao_token";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) ?? "";
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(init.headers);
  if (!(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers
  });

  if (!response.ok) {
    let message = "请求失败";
    try {
      const body = await response.json();
      message = body.detail ?? message;
    } catch {
      message = response.statusText || message;
    }
    throw new ApiError(message, response.status);
  }

  return response.json() as Promise<T>;
}

export async function login(username: string, password: string): Promise<{ token: string; user: User }> {
  return request("/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password })
  });
}

export async function getMe(): Promise<User> {
  return request("/me");
}

export async function listExpenses(): Promise<Expense[]> {
  return request("/expenses");
}

export async function listInvoicePool(): Promise<InvoicePoolItem[]> {
  return request("/invoice-pool");
}

export async function createExpenseAllocation(payload: ExpenseAllocationCreatePayload): Promise<Expense> {
  return request("/expense-allocations", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function createExpenseAllocationsBatch(payload: ExpenseAllocationBatchCreatePayload): Promise<Expense> {
  return request("/expense-allocations/batch", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function linkExpenseAttachments(id: number, payload: ExpenseAttachmentLinkPayload): Promise<Expense> {
  return request(`/expenses/${id}/attachments`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function deleteExpense(id: number): Promise<{ deleted: boolean }> {
  return request(`/expenses/${id}`, {
    method: "DELETE"
  });
}

export async function deleteExpenseAttachment(expenseId: number, attachmentId: number): Promise<Expense> {
  return request(`/expenses/${expenseId}/attachments/${attachmentId}`, {
    method: "DELETE"
  });
}

export async function deleteAttachment(id: number): Promise<{ deleted: boolean }> {
  return request(`/attachments/${id}`, {
    method: "DELETE"
  });
}

export async function addAttachmentsToInvoicePool(attachmentIds: number[]): Promise<Attachment[]> {
  return request("/attachments/pool", {
    method: "POST",
    body: JSON.stringify({ attachment_ids: attachmentIds })
  });
}

export async function createExpense(payload: ExpenseCreatePayload): Promise<Expense> {
  return request("/expenses", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function createExpenseDraft(payload: DraftExpenseCreatePayload): Promise<Expense> {
  return request("/expenses/drafts", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function completeExpenseDraft(id: number, payload: DraftExpenseCompletePayload): Promise<Expense> {
  return request(`/expenses/drafts/${id}/complete`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function createExpensesBatch(items: ExpenseItemCreatePayload[]): Promise<Expense[]> {
  return request("/expenses/batch", {
    method: "POST",
    body: JSON.stringify({ items })
  });
}

export async function uploadAttachment(file: File): Promise<Attachment> {
  const body = new FormData();
  body.append("file", file);
  return request("/attachments", {
    method: "POST",
    body
  });
}

export async function uploadAttachments(files: File[]): Promise<Attachment[]> {
  const body = new FormData();
  files.forEach((file) => body.append("files", file));
  return request("/attachments/batch", {
    method: "POST",
    body
  });
}

export async function getAttachmentObjectUrl(id: number): Promise<{ url: string; contentType: string }> {
  const token = getToken();
  const response = await fetch(`${API_BASE}/attachments/${id}/content`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {}
  });
  if (!response.ok) {
    throw new ApiError("附件预览失败", response.status);
  }
  const blob = await response.blob();
  return {
    url: URL.createObjectURL(blob),
    contentType: blob.type
  };
}

export async function listLedger(filters: Record<string, string>): Promise<LedgerRow[]> {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value) params.set(key, value);
  });
  const query = params.toString();
  return request(`/admin/ledger${query ? `?${query}` : ""}`);
}

export async function getExportPreview(filters: Record<string, string>): Promise<ExportPreview> {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value) params.set(key, value);
  });
  const query = params.toString();
  return request(`/admin/export/preview${query ? `?${query}` : ""}`);
}

export async function downloadExport(filters: Record<string, string>): Promise<void> {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value) params.set(key, value);
  });
  const token = getToken();
  const response = await fetch(`${API_BASE}/admin/export.xlsx?${params.toString()}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {}
  });
  if (!response.ok) {
    throw new ApiError("导出失败", response.status);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `报销台账-${filters.month || "全部"}.xlsx`;
  link.click();
  URL.revokeObjectURL(url);
}

export async function downloadExportPackage(filters: Record<string, string>): Promise<void> {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value) params.set(key, value);
  });
  const token = getToken();
  const response = await fetch(`${API_BASE}/admin/export-package.zip?${params.toString()}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {}
  });
  if (!response.ok) {
    throw new ApiError("导出明细包失败", response.status);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${exportMonthLabel(filters.month)}报销明细包.zip`;
  link.click();
  URL.revokeObjectURL(url);
}

function exportMonthLabel(month: string | undefined): string {
  if (!month) return "全部";
  const match = month.match(/^\d{4}-(\d{2})$/);
  return match ? `${Number(match[1])}月` : month;
}

export async function listUsers(): Promise<AdminUser[]> {
  return request("/admin/users");
}

export async function createUser(payload: AdminUserCreatePayload): Promise<AdminUser> {
  return request("/admin/users", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function updateUser(id: number, payload: AdminUserUpdatePayload): Promise<AdminUser> {
  return request(`/admin/users/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload)
  });
}

export async function deactivateUser(id: number): Promise<AdminUser> {
  return request(`/admin/users/${id}`, {
    method: "DELETE"
  });
}
