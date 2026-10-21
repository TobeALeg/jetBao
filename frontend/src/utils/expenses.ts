import type { Expense } from "../types";

// Keep earlier drafts actionable without changing their original reimbursement month.
export function isExpenseInMonthlyWorkspace(
  expense: Pick<Expense, "expense_month" | "status">,
  month: string
): boolean {
  return expense.expense_month === month
    || (expense.expense_month < month && expense.status === "pending");
}
