export const EXPENSE_CATEGORIES = ["差旅交通", "餐饮招待", "办公采购", "AI 项目", "市场活动"] as const;

export type ExpenseCategory = (typeof EXPENSE_CATEGORIES)[number];

export const DEFAULT_EXPENSE_CATEGORY: ExpenseCategory = "差旅交通";
