import type {
  AdminUser,
  AdminUserCreatePayload,
  AdminUserUpdatePayload,
  Attachment,
  Expense,
  ExpenseCreatePayload,
  ExpenseItemCreatePayload,
  ExportPreview,
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

export async function createExpense(payload: ExpenseCreatePayload): Promise<Expense> {
  return request("/expenses", {
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
