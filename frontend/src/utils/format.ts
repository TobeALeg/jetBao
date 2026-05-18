export function formatCurrency(value: number | null | undefined): string {
  if (value === null || value === undefined) return "-";
  return new Intl.NumberFormat("zh-CN", {
    style: "currency",
    currency: "CNY",
    maximumFractionDigits: 2
  }).format(value);
}

export function formatDate(value: string): string {
  if (!value) return "-";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(value.replace(" ", "T")));
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function currentMonth(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  return `${now.getFullYear()}-${month}`;
}

export function currentReimbursementMonth(): string {
  const now = new Date();
  const reimbursementDate = new Date(now);
  if (now.getDate() < 15) {
    reimbursementDate.setMonth(reimbursementDate.getMonth() - 1);
  }
  const month = String(reimbursementDate.getMonth() + 1).padStart(2, "0");
  return `${reimbursementDate.getFullYear()}-${month}`;
}
