<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { CheckCircle2, FilePlus2, ImagePlus, Loader2, Plus } from "lucide-vue-next";
import AttachmentPreviewModal from "../components/AttachmentPreviewModal.vue";
import UploadAttachmentTile from "../components/UploadAttachmentTile.vue";
import { buyerMatchStatus, isDifferentAllowedBuyer } from "../constants/companyEntities";
import { DEFAULT_EXPENSE_CATEGORY, EXPENSE_CATEGORIES } from "../constants/expenseCategories";
import {
  createExpenseAllocationsBatch,
  createAndSubmitExpense,
  createExpenseDraft,
  deleteAttachment,
  deleteExpense,
  deleteExpenseAttachment,
  deleteExpenseInvoiceAttachment,
  linkExpenseAttachments,
  listExpenses,
  submitExpense,
  uploadAttachments,
  uploadInvoiceAttachments,
  withdrawExpense,
} from "../services/api";
import { currentReimbursementMonth, formatCurrency } from "../utils/format";
import type { Attachment, Expense, ExpenseCreatePayload } from "../types";

const props = defineProps<{
  user: { company_entity: string };
  refreshKey: number;
}>();

const emit = defineEmits<{
  refreshed: [];
}>();

type RecordState = "missing_material" | "ready" | "rejected" | "submitted" | "approved";
type TableSection = { key: "active" | "submitted" | "approved"; records: Expense[] };

const month = currentReimbursementMonth();
const expenses = ref<Expense[]>([]);
const loading = ref(false);
const saving = ref(false);
const error = ref("");
const success = ref("");
const isComposerOpen = ref(true);
const targetExpenseId = ref<number | null>(null);
const isNewSubstitute = ref(false);
const substituteReason = ref("");
const evidenceAttachments = ref<Attachment[]>([]);
const stagedInvoices = ref<Attachment[]>([]);
const substituteReasonInput = ref<HTMLTextAreaElement | null>(null);
const evidenceInput = ref<HTMLInputElement | null>(null);
const invoiceInput = ref<HTMLInputElement | null>(null);
const evidenceDragging = ref(false);
const invoiceDragging = ref(false);
const previewAttachment = ref<Attachment | null>(null);
const removingAttachmentId = ref<number | null>(null);

const expenseForm = ref<{ project_name: string; actual_amount: string; category: string }>({
  project_name: "",
  actual_amount: "",
  category: DEFAULT_EXPENSE_CATEGORY,
});

const currentMonthExpenses = computed(() => expenses.value.filter((expense) => expense.expense_month === month));
const submittedRecords = computed(() => currentMonthExpenses.value.filter((expense) => expense.status === "matched"));
const approvedRecords = computed(() => currentMonthExpenses.value.filter((expense) => expense.status === "reviewed"));
const submittedTotal = computed(() => submittedRecords.value.reduce((sum, record) => sum + Number(record.actual_amount), 0));
const approvedTotal = computed(() => approvedRecords.value.reduce((sum, record) => sum + Number(record.actual_amount), 0));
const materialMissingCount = computed(() => currentMonthExpenses.value.filter((record) => record.status === "pending" && !record.reject_reason && (!record.allocation_count || !record.attachments.length)).length);
const materialMissingTotal = computed(() => currentMonthExpenses.value
  .filter((record) => record.status === "pending" && !record.reject_reason && (!record.allocation_count || !record.attachments.length))
  .reduce((sum, record) => sum + Number(record.actual_amount), 0));
const rejectedCount = computed(() => currentMonthExpenses.value.filter((record) => record.status === "pending" && Boolean(record.reject_reason)).length);
function activeRecordPriority(expense: Expense): number {
  if (expense.reject_reason) return 0;
  if (recordState(expense) === "ready") return 1;
  return 2;
}
const tableSections = computed<TableSection[]>(() => {
  const active = currentMonthExpenses.value
    .filter((record) => record.status === "pending")
    .sort((a, b) => activeRecordPriority(a) - activeRecordPriority(b));
  const submitted = currentMonthExpenses.value.filter((record) => record.status === "matched");
  const approved = currentMonthExpenses.value.filter((record) => record.status === "reviewed");
  return [
    ...(active.length ? [{ key: "active" as const, records: active }] : []),
    ...(submitted.length ? [{ key: "submitted" as const, records: submitted }] : []),
    ...(approved.length ? [{ key: "approved" as const, records: approved }] : []),
  ];
});
const targetExpense = computed(() => expenses.value.find((expense) => expense.id === targetExpenseId.value) ?? null);
const isEditingPendingExpense = computed(() => Boolean(targetExpenseId.value && targetExpense.value?.status === "pending"));
const stagedInvoiceItems = computed(() => invoiceReferencesOf(stagedInvoices.value));
const stagedInvoiceTotal = computed(() => roundMoney(stagedInvoiceItems.value.reduce((sum, invoice) => sum + Number(invoice.item.amount), 0)));
const linkedInvoiceAmount = computed(() => {
  if (stagedInvoices.value.length) return stagedInvoiceTotal.value;
  const expense = targetExpense.value;
  if (!expense?.allocations.length) return 0;
  return roundMoney(expense.allocations.reduce((sum, item) => sum + Number(item.invoice_amount || 0), 0));
});
const formActualAmount = computed(() => Number(expenseForm.value.actual_amount) || 0);
const amountsMismatch = computed(() => {
  const invoiceAmount = linkedInvoiceAmount.value || stagedInvoiceTotal.value;
  const actualAmount = formActualAmount.value || Number(targetExpense.value?.actual_amount || 0);
  return invoiceAmount > 0 && actualAmount > 0 && roundMoney(invoiceAmount) !== roundMoney(actualAmount);
});
const invoiceAmountExceedsExpense = computed(() => {
  const actualAmount = formActualAmount.value || Number(targetExpense.value?.actual_amount || 0);
  return actualAmount > 0 && linkedInvoiceAmount.value > actualAmount;
});
const showSubstituteReason = computed(() => isNewSubstitute.value || invoiceAmountExceedsExpense.value);
const canSubmitNew = computed(() => Boolean(stagedInvoiceItems.value.length && Number(expenseForm.value.actual_amount) > 0 && stagedInvoiceTotal.value >= Number(expenseForm.value.actual_amount)));
const canSubmitExisting = computed(() => Boolean(isEditingPendingExpense.value && targetExpense.value && targetExpense.value.allocation_count > 0 && targetExpense.value.remaining_amount <= 0));
const displayEvidenceAttachments = computed(() => [...(isEditingPendingExpense.value ? targetExpense.value?.attachments ?? [] : []), ...evidenceAttachments.value]);
const displayInvoiceAttachments = computed<Attachment[]>(() => {
  if (stagedInvoices.value.length) return stagedInvoices.value;
  const expense = isEditingPendingExpense.value ? targetExpense.value : null;
  return expense?.invoice_attachments ?? [];
});
const displayInvoiceItems = computed(() => {
  if (stagedInvoices.value.length) return stagedInvoiceItems.value;
  const expense = isEditingPendingExpense.value ? targetExpense.value : null;
  if (!expense?.allocations.length) return [];
  return expense.allocations.map((allocation) => {
    const attachment = (expense.invoice_attachments ?? []).find((item) => item.id === allocation.attachment_id);
    const ocrItem = attachment ? invoiceItemsOf(attachment)[allocation.invoice_item_index] : null;
    return {
      attachment_id: allocation.attachment_id,
      invoice_item_index: allocation.invoice_item_index,
      item: ocrItem ?? {
        amount: allocation.invoice_amount,
        buyer: allocation.invoice_buyer,
        invoice_number: allocation.invoice_number,
        date: allocation.invoice_date,
        sub_type_description: allocation.invoice_type,
      },
    };
  });
});
const canRemoveInvoice = computed(() => {
  if (stagedInvoices.value.length) return true;
  const expense = targetExpense.value;
  return Boolean(expense?.allocation_count && expense.status === "pending");
});
const invoiceUploadLocked = computed(() => saving.value);

function roundMoney(value: number): number {
  return Math.round(value * 100) / 100;
}

function recordState(expense: Expense): RecordState {
  if (expense.status === "reviewed") return "approved";
  if (expense.status === "matched") return "submitted";
  if (expense.status === "pending" && expense.reject_reason) return "rejected";
  if (expense.status === "pending" && (expense.allocation_count === 0 || expense.remaining_amount > 0)) return "missing_material";
  if (expense.status === "pending") return "ready";
  return "submitted";
}

function recordStateLabel(expense: Expense): string {
  const state = recordState(expense);
  if (state === "missing_material") return "待补材料";
  if (state === "ready") return "待提交";
  if (state === "rejected") return "已打回";
  if (state === "approved") return "已完成";
  return "已提交";
}

function recordStateClass(expense: Expense): string {
  const state = recordState(expense);
  if (state === "missing_material") return "bg-amber-100 text-amber-800";
  if (state === "ready") return "bg-teal-50 text-teal-800";
  if (state === "rejected") return "bg-rose-50 text-rose-700";
  if (state === "approved") return "bg-slate-100 text-slate-500";
  return "bg-slate-100 text-slate-600";
}

function tableRowClass(sectionKey: TableSection["key"], record: Expense): string {
  if (sectionKey === "approved" || recordState(record) === "approved") {
    return "bg-slate-50/80 text-slate-500";
  }
  if (recordState(record) === "rejected") {
    return "bg-rose-50/30 hover:bg-rose-50/50";
  }
  return "hover:bg-slate-50";
}

function tableSectionClass(sectionKey: TableSection["key"]): string {
  if (sectionKey === "approved") return "border-t-4 border-slate-300";
  if (sectionKey === "submitted") return "border-t-4 border-slate-200";
  return "";
}

function resetComposer() {
  targetExpenseId.value = null;
  evidenceAttachments.value = [];
  stagedInvoices.value = [];
  isNewSubstitute.value = false;
  substituteReason.value = "";
  expenseForm.value = { project_name: "", actual_amount: "", category: DEFAULT_EXPENSE_CATEGORY };
}

function setSubstitute(value: boolean) {
  isNewSubstitute.value = value;
  if (value) {
    error.value = "";
    requestAnimationFrame(() => {
      substituteReasonInput.value?.focus();
    });
  } else {
    substituteReason.value = "";
  }
}

function startNewExpense() {
  resetComposer();
  isComposerOpen.value = true;
  error.value = "";
  success.value = "";
}

function syncComposerWithLoadedExpenses() {
  if (!targetExpenseId.value) return;
  const current = expenses.value.find((expense) => expense.id === targetExpenseId.value);
  if (!current || current.status !== "pending") {
    resetComposer();
    if (current?.status === "reviewed") {
      isComposerOpen.value = false;
      success.value = "该报销已完成审核。";
    }
  }
}

function openExistingExpense(expense: Expense) {
  if (expense.status !== "pending") return;
  targetExpenseId.value = expense.id;
  isComposerOpen.value = true;
  isNewSubstitute.value = expense.is_substitute;
  substituteReason.value = expense.substitute_reason || "";
  expenseForm.value = {
    project_name: expense.project_name,
    actual_amount: String(expense.actual_amount),
    category: expense.category,
  };
  evidenceAttachments.value = [];
  stagedInvoices.value = [];
  error.value = "";
  success.value = expense.reject_reason ? "此报销已被打回，请修改后重新提交。" : "";
  window.scrollTo({ top: 0, behavior: "smooth" });
}

async function load() {
  loading.value = true;
  error.value = "";
  try {
    expenses.value = await listExpenses();
    syncComposerWithLoadedExpenses();
    emit("refreshed");
  } catch (err) {
    error.value = err instanceof Error ? err.message : "加载报销记录失败";
  } finally {
    loading.value = false;
  }
}

function invoiceItemsOf(attachment: Attachment): Array<Record<string, unknown>> {
  return Array.isArray(attachment.ocr_result.invoice_items)
    ? attachment.ocr_result.invoice_items.filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object"))
    : [];
}

function invoiceText(item: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    const value = item[key];
    if (value !== null && value !== undefined && value !== "") return String(value);
  }
  return "待识别";
}

function isBuyerConfirmationNeeded(item: Record<string, unknown>): boolean {
  const buyer = invoiceText(item, ["buyer"]);
  const status = buyerMatchStatus(buyer);
  return status === "partial" || (status === "exact" && isDifferentAllowedBuyer(buyer, props.user.company_entity));
}

type PreparedInvoiceBatch = {
  invoices: Array<{ attachment_id: number; invoice_item_index: number }>;
  note: string;
  buyerConfirmed: boolean;
};

type InvoiceReference = {
  attachment_id: number;
  invoice_item_index: number;
  item: Record<string, unknown>;
};

function invoiceReferencesOf(attachments: Attachment[]): InvoiceReference[] {
  return attachments.flatMap((attachment) => invoiceItemsOf(attachment)
    .map((item, index) => ({ attachment_id: attachment.id, invoice_item_index: index, item }))
    .filter(({ item }) => typeof item.amount === "number" && Number(item.amount) > 0));
}

function prepareInvoiceLinks(
  attachments: Attachment[],
  actualAmount: number,
  isSubstitute: boolean,
  reason = "",
  existingAmount = 0,
  requireCoverage = false
): PreparedInvoiceBatch {
  const invoices = invoiceReferencesOf(attachments);
  if (!invoices.length) throw new Error("发票未识别到有效金额，请重新上传");
  const expenseAmount = roundMoney(actualAmount);
  const invoiceAmount = roundMoney(existingAmount + invoices.reduce((sum, invoice) => sum + Number(invoice.item.amount), 0));

  if (requireCoverage && invoiceAmount < expenseAmount) {
    throw new Error("发票金额不足，请补充金额更足的发票");
  }
  if (invoiceAmount > expenseAmount && !isSubstitute) {
    throw new Error("发票合计高于报销金额，请选择「替票」并填写替票说明");
  }

  let note = "";
  if (isSubstitute && invoiceAmount !== expenseAmount && (requireCoverage || invoiceAmount > expenseAmount)) {
    note = reason.trim();
    if (!note) {
      setSubstitute(true);
      throw new Error("请填写替票说明后再提交");
    }
  }

  const needsBuyerConfirmation = invoices.some((invoice) => isBuyerConfirmationNeeded(invoice.item));
  const buyerConfirmed = needsBuyerConfirmation
    ? window.confirm("部分发票的购买方需要人工确认，确认继续吗？")
    : false;
  if (needsBuyerConfirmation && !buyerConfirmed) throw new Error("已取消提交，请确认发票购买方");
  return {
    invoices: invoices.map(({ attachment_id, invoice_item_index }) => ({ attachment_id, invoice_item_index })),
    note,
    buyerConfirmed,
  };
}

async function linkInvoicesToExpense(expenseId: number, prepared: PreparedInvoiceBatch): Promise<Expense> {
  return createExpenseAllocationsBatch({
    expense_id: expenseId,
    invoices: prepared.invoices,
    note: prepared.note,
    buyer_confirmed: prepared.buyerConfirmed,
  });
}

function withUploadPreview(files: File[], uploaded: Attachment[]): Attachment[] {
  return uploaded.map((attachment, index) => {
    const file = files[index];
    if (!file?.type.startsWith("image/")) return attachment;
    return { ...attachment, preview_url: URL.createObjectURL(file) };
  });
}

function isStagedEvidence(attachment: Attachment): boolean {
  return evidenceAttachments.value.some((item) => item.id === attachment.id);
}

function openAttachmentPreview(attachment: Attachment) {
  previewAttachment.value = attachment;
}

function closeAttachmentPreview() {
  previewAttachment.value = null;
}

async function removeEvidenceAttachment(attachment: Attachment) {
  if (!window.confirm("确认删除这份佐证材料？")) return;
  removingAttachmentId.value = attachment.id;
  error.value = "";
  try {
    if (targetExpenseId.value && !isStagedEvidence(attachment)) {
      await deleteExpenseAttachment(targetExpenseId.value, attachment.id);
      await load();
    } else {
      await deleteAttachment(attachment.id);
      evidenceAttachments.value = evidenceAttachments.value.filter((item) => item.id !== attachment.id);
    }
    success.value = "佐证材料已删除";
  } catch (err) {
    error.value = err instanceof Error ? err.message : "佐证材料删除失败";
  } finally {
    removingAttachmentId.value = null;
  }
}

async function removeInvoiceAttachment(attachment: Attachment) {
  const invoiceCount = invoiceReferencesOf([attachment]).length;
  const message = invoiceCount > 1
    ? `这份文件识别出 ${invoiceCount} 张发票，确认全部删除？`
    : "确认删除这张发票？";
  if (!window.confirm(message)) return;
  removingAttachmentId.value = attachment.id;
  error.value = "";
  try {
    if (targetExpenseId.value && targetExpense.value?.allocation_count) {
      await deleteExpenseInvoiceAttachment(targetExpenseId.value, attachment.id);
      await load();
    } else {
      await deleteAttachment(attachment.id);
      stagedInvoices.value = stagedInvoices.value.filter((item) => item.id !== attachment.id);
    }
    success.value = "发票已删除";
  } catch (err) {
    error.value = err instanceof Error ? err.message : "发票删除失败";
  } finally {
    removingAttachmentId.value = null;
  }
}

async function handleEvidenceFiles(files: File[]) {
  if (!files.length) return;
  saving.value = true;
  error.value = "";
  try {
    const uploaded = withUploadPreview(files, await uploadAttachments(files));
    if (targetExpenseId.value) {
      await linkExpenseAttachments(targetExpenseId.value, { attachment_ids: uploaded.map((item) => item.id) });
      await load();
      success.value = `已上传 ${uploaded.length} 份佐证材料`;
    } else {
      evidenceAttachments.value = [...evidenceAttachments.value, ...uploaded];
      success.value = `已选择 ${evidenceAttachments.value.length} 份佐证材料`;
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : "佐证材料上传失败";
  } finally {
    saving.value = false;
  }
}

async function handleInvoiceFiles(files: File[]) {
  if (!files.length) return;
  if (invoiceUploadLocked.value) return;
  saving.value = true;
  error.value = "";
  try {
    const uploaded = withUploadPreview(files, await uploadInvoiceAttachments(files));
    const recognizedCount = invoiceReferencesOf(uploaded).length;
    if (!recognizedCount) throw new Error("未识别到有效发票，请重新上传");
    if (targetExpenseId.value) {
      const prepared = prepareInvoiceLinks(
        uploaded,
        Number(expenseForm.value.actual_amount),
        isNewSubstitute.value,
        substituteReason.value,
        Number(targetExpense.value?.allocated_amount || 0)
      );
      await linkInvoicesToExpense(targetExpenseId.value, prepared);
      await load();
      success.value = `已识别并关联 ${recognizedCount} 张发票`;
    } else {
      stagedInvoices.value = [...stagedInvoices.value, ...uploaded];
      success.value = `已识别 ${stagedInvoiceItems.value.length} 张发票`;
    }
  } catch (err) {
    success.value = "";
    error.value = err instanceof Error ? err.message : "发票上传失败";
  } finally {
    saving.value = false;
  }
}

function handleEvidenceInput(event: Event) {
  const input = event.target as HTMLInputElement;
  void handleEvidenceFiles(Array.from(input.files ?? []));
  input.value = "";
}

function handleInvoiceInput(event: Event) {
  const input = event.target as HTMLInputElement;
  void handleInvoiceFiles(Array.from(input.files ?? []));
  input.value = "";
}

function handleEvidenceDrop(event: DragEvent) {
  evidenceDragging.value = false;
  void handleEvidenceFiles(Array.from(event.dataTransfer?.files ?? []));
}

function handleInvoiceDrop(event: DragEvent) {
  invoiceDragging.value = false;
  void handleInvoiceFiles(Array.from(event.dataTransfer?.files ?? []));
}

async function saveNewExpense(submitAfter: boolean) {
  const projectName = expenseForm.value.project_name.trim();
  const actualAmount = Number(expenseForm.value.actual_amount);
  if (!projectName) throw new Error("请填写报销事项");
  if (!actualAmount || actualAmount <= 0) throw new Error("请填写金额");

  const payload: ExpenseCreatePayload = {
    project_name: projectName,
    actual_amount: actualAmount,
    expense_month: month,
    category: expenseForm.value.category,
    is_substitute: isNewSubstitute.value,
  };
  const prepared = stagedInvoices.value.length
    ? prepareInvoiceLinks(stagedInvoices.value, actualAmount, isNewSubstitute.value, substituteReason.value, 0, submitAfter)
    : null;
  const reason = (prepared?.note || substituteReason.value).trim();
  if (isNewSubstitute.value && amountsMismatch.value && !reason) {
    setSubstitute(true);
    throw new Error("请填写替票说明后再提交");
  }
  if (submitAfter) {
    if (!stagedInvoices.value.length || !prepared) throw new Error("请先上传发票");
    return createAndSubmitExpense({
      ...payload,
      is_substitute: isNewSubstitute.value,
      substitute_reason: reason,
      invoices: prepared.invoices,
      attachment_ids: evidenceAttachments.value.map((item) => item.id),
      note: prepared.note,
      buyer_confirmed: prepared.buyerConfirmed,
    });
  }

  let created = await createExpenseDraft({
    ...payload,
    is_substitute: isNewSubstitute.value,
    substitute_reason: reason,
  });
  if (evidenceAttachments.value.length) {
    created = await linkExpenseAttachments(created.id, { attachment_ids: evidenceAttachments.value.map((item) => item.id) });
  }
  if (stagedInvoices.value.length) {
    created = await linkInvoicesToExpense(created.id, prepared as PreparedInvoiceBatch);
  }
  return created;
}

async function saveDraft() {
  if (targetExpenseId.value) {
    isComposerOpen.value = false;
    return;
  }
  saving.value = true;
  error.value = "";
  success.value = "";
  try {
    const created = await saveNewExpense(false);
    success.value = `「${created.project_name}」已保存到待补材料`;
    resetComposer();
    await load();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "保存失败";
  } finally {
    saving.value = false;
  }
}

async function submitCurrent() {
  saving.value = true;
  error.value = "";
  success.value = "";
  try {
    if (targetExpenseId.value) {
      const current = expenses.value.find((expense) => expense.id === targetExpenseId.value);
      if (!current || !canSubmitExisting.value) throw new Error("请先补齐发票后再提交");
      if (amountsMismatch.value && !isNewSubstitute.value) {
        setSubstitute(true);
        throw new Error("发票金额与报销金额不一致，请选择「替票」并填写替票说明");
      }
      if (isNewSubstitute.value && amountsMismatch.value && !substituteReason.value.trim()) {
        setSubstitute(true);
        throw new Error("请填写替票说明后再提交");
      }
      await submitExpense(current.id, {
        is_substitute: isNewSubstitute.value,
        substitute_reason: substituteReason.value.trim(),
      });
      success.value = "报销已提交";
    } else {
      const created = await saveNewExpense(true);
      success.value = `「${created.project_name}」已提交`;
    }
    resetComposer();
    await load();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "提交失败";
  } finally {
    saving.value = false;
  }
}

async function submitRecord(record: Expense) {
  saving.value = true;
  error.value = "";
  try {
    await submitExpense(record.id);
    success.value = "报销已提交";
    await load();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "提交失败";
  } finally {
    saving.value = false;
  }
}

async function withdraw(record: Expense) {
  saving.value = true;
  error.value = "";
  try {
    await withdrawExpense(record.id);
    success.value = "报销已撤回";
    await load();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "撤回失败";
  } finally {
    saving.value = false;
  }
}

async function deleteRecord(record: Expense) {
  if (!window.confirm("确认删除此笔待补材料报销？此操作不可恢复。")) return;
  saving.value = true;
  error.value = "";
  try {
    await deleteExpense(record.id);
    success.value = "待补材料报销已删除";
    await load();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "删除失败";
  } finally {
    saving.value = false;
  }
}

onMounted(() => {
  void load();
  document.addEventListener("visibilitychange", handleVisibilityChange);
});
onBeforeUnmount(() => {
  document.removeEventListener("visibilitychange", handleVisibilityChange);
});
watch(() => props.refreshKey, load);
watch(targetExpense, (expense) => {
  if (!targetExpenseId.value || !expense) return;
  if (expense.status !== "pending") {
    resetComposer();
    if (expense.status === "reviewed") {
      isComposerOpen.value = false;
    }
  }
});

function handleVisibilityChange() {
  if (document.visibilityState === "visible") void load();
}
</script>

<template>
  <div class="mx-auto max-w-6xl space-y-7">
    <header class="space-y-5 border-b border-slate-200 pb-5">
      <div class="flex flex-wrap items-end justify-between gap-5">
        <div>
          <p class="text-xs font-semibold uppercase tracking-[0.16em] text-teal-700">JetBao / {{ month }}</p>
          <h1 class="mt-2 text-3xl font-semibold tracking-tight text-ink">个人报销</h1>
        </div>
      </div>
      <div class="grid gap-3 sm:grid-cols-3">
        <div class="rounded-3xl border border-teal-100 bg-teal-50 p-5 shadow-sm">
          <p class="text-xs font-semibold uppercase tracking-[0.18em] text-teal-700">已提交</p>
          <div class="mt-4">
            <p class="text-3xl font-semibold text-ink">{{ formatCurrency(submittedTotal) }}</p>
            <p class="mt-2 text-sm text-slate-600">{{ submittedRecords.length }} 笔待审核</p>
          </div>
        </div>
        <div class="rounded-3xl border border-rose-100 bg-rose-50 p-5 shadow-sm">
          <p class="text-xs font-semibold uppercase tracking-[0.18em] text-rose-700">已打回</p>
          <div class="mt-4">
            <p class="text-3xl font-semibold text-rose-900">{{ rejectedCount }}</p>
            <p class="mt-2 text-sm text-slate-600">需修改后重新提交</p>
          </div>
        </div>
        <div class="rounded-3xl border border-orange-100 bg-orange-50 p-5 shadow-sm">
          <p class="text-xs font-semibold uppercase tracking-[0.18em] text-orange-700">待补材料</p>
          <div class="mt-4">
            <p class="text-3xl font-semibold text-orange-900">{{ formatCurrency(materialMissingTotal) }}</p>
            <p class="mt-2 text-sm text-slate-600">{{ materialMissingCount }} 笔</p>
          </div>
        </div>
      </div>
      <div v-if="approvedRecords.length" class="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
        已完成 {{ approvedRecords.length }} 笔，合计 {{ formatCurrency(approvedTotal) }}（见下方灰色记录）
      </div>
    </header>

    <p v-if="error" class="border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">{{ error }}</p>
    <p v-if="success" class="border border-teal-200 bg-teal-50 px-4 py-3 text-sm text-teal-800">{{ success }}</p>

    <div v-if="!isComposerOpen" class="flex justify-end pt-4">
      <button class="primary-button h-10 px-4" type="button" @click="startNewExpense()">
        <Plus class="h-4 w-4" />
        新建报销
      </button>
    </div>

    <section v-if="isComposerOpen" class="border-y border-slate-200 bg-white">
      <div v-if="isEditingPendingExpense && targetExpense?.reject_reason" class="border-b border-rose-200 bg-rose-50 px-5 py-3 text-sm text-rose-800">
        <span class="font-medium">管理员打回：</span>{{ targetExpense.reject_reason }}
      </div>
      <div class="p-5">
        <div class="grid gap-x-7 gap-y-5 lg:grid-cols-[minmax(0,1fr)_150px_190px_150px]">
          <label class="block"><span class="block text-[11px] font-semibold tracking-[0.08em] text-slate-400">报销事项</span><input v-model="expenseForm.project_name" :disabled="isEditingPendingExpense" class="mt-1 h-9 w-full border-0 border-b border-slate-300 bg-transparent p-0 text-[15px] font-medium text-ink outline-none transition hover:border-slate-400 hover:bg-slate-50 focus:border-teal-700 disabled:text-slate-500" placeholder="填写报销事项" /></label>
          <label class="block"><span class="block text-[11px] font-semibold tracking-[0.08em] text-slate-400">金额</span><input v-model="expenseForm.actual_amount" :disabled="isEditingPendingExpense" class="mt-1 h-9 w-full border-0 border-b border-slate-300 bg-transparent p-0 text-[15px] font-medium text-ink outline-none transition hover:border-slate-400 hover:bg-slate-50 focus:border-teal-700 disabled:text-slate-500" inputmode="decimal" placeholder="0.00" /></label>
          <label class="block"><span class="block text-[11px] font-semibold tracking-[0.08em] text-slate-400">类别</span><select v-model="expenseForm.category" :disabled="isEditingPendingExpense" class="mt-1 h-9 w-full border-0 border-b border-slate-300 bg-transparent p-0 text-[15px] font-medium text-ink outline-none transition hover:border-slate-400 hover:bg-slate-50 focus:border-teal-700 disabled:text-slate-500"><option v-for="category in EXPENSE_CATEGORIES" :key="category">{{ category }}</option></select></label>
          <div>
            <span class="block text-[11px] font-semibold tracking-[0.08em] text-slate-400">替票</span>
            <div class="mt-1 flex h-9 items-center gap-4 border-b border-slate-300 text-[14px] font-medium">
              <button
                class="h-full border-b-2 px-1 transition"
                :class="!isNewSubstitute ? 'border-slate-800 text-ink' : 'border-transparent text-slate-400 hover:text-slate-700'"
                type="button"
                @click="setSubstitute(false)"
              >
                否
              </button>
              <button
                class="h-full border-b-2 px-1 transition"
                :class="isNewSubstitute ? 'border-orange-500 text-orange-700' : 'border-transparent text-slate-400 hover:text-slate-700'"
                type="button"
                @click="setSubstitute(true)"
              >
                是
              </button>
            </div>
          </div>
        </div>

        <div v-if="showSubstituteReason" class="mt-5 rounded-lg border border-orange-200 bg-orange-50/70 px-4 py-3">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <label class="text-sm font-medium text-orange-900" for="substitute-reason-input">替票说明</label>
            <span v-if="amountsMismatch && !isNewSubstitute" class="text-xs text-orange-700">金额不一致，请先选择替票「是」</span>
            <span v-else-if="amountsMismatch" class="text-xs text-orange-700">票面与报销金额不一致，须填写说明</span>
          </div>
          <textarea
            id="substitute-reason-input"
            ref="substituteReasonInput"
            v-model="substituteReason"
            class="mt-2 min-h-[84px] w-full rounded-md border border-orange-200 bg-white px-3 py-2 text-sm text-slate-800 outline-none transition focus:border-orange-400 focus:ring-2 focus:ring-orange-200"
            :disabled="!isNewSubstitute"
            :placeholder="isNewSubstitute ? '例如：发票含其他项目，本次仅报销其中一部分' : '选择替票「是」后在此填写说明'"
          />
        </div>
      </div>

      <input ref="evidenceInput" class="hidden" type="file" accept="image/*,.pdf" multiple @change="handleEvidenceInput" />
      <input ref="invoiceInput" class="hidden" type="file" accept="image/*,.pdf" multiple @change="handleInvoiceInput" />
      <div class="grid gap-px border-y border-slate-200 bg-slate-200 lg:grid-cols-2">
        <div class="space-y-3 bg-white p-5">
          <div class="flex items-center justify-between"><span class="field-label">上传佐证材料</span><span class="text-xs text-slate-500">可一次上传多张</span></div>
          <div
            class="upload-zone min-h-28 w-full border border-dashed transition"
            :class="evidenceDragging ? 'border-teal-600 bg-teal-50' : 'border-slate-300 bg-slate-50'"
            @dragenter.prevent="evidenceDragging = true"
            @dragover.prevent="evidenceDragging = true"
            @dragleave.prevent="evidenceDragging = false"
            @drop.prevent="handleEvidenceDrop"
          >
            <div v-if="displayEvidenceAttachments.length" class="grid grid-cols-2 gap-2 p-3 sm:grid-cols-3">
              <UploadAttachmentTile
                v-for="attachment in displayEvidenceAttachments"
                :key="attachment.id"
                :attachment="attachment"
                :removable="isEditingPendingExpense && !saving"
                :removing="removingAttachmentId === attachment.id"
                @preview="openAttachmentPreview"
                @remove="removeEvidenceAttachment"
              />
              <button
                class="flex aspect-square flex-col items-center justify-center rounded-lg border border-dashed border-slate-300 bg-white text-slate-500 transition hover:border-teal-600 hover:bg-teal-50 hover:text-teal-700 disabled:cursor-not-allowed disabled:opacity-60"
                :disabled="saving"
                type="button"
                @click="evidenceInput?.click()"
              >
                <Loader2 v-if="saving" class="h-5 w-5 animate-spin" />
                <ImagePlus v-else class="h-5 w-5" />
                <span class="mt-1 text-[11px] font-medium">继续上传</span>
              </button>
            </div>
            <button
              v-else
              class="flex min-h-28 w-full flex-col items-center justify-center px-4 text-center transition hover:bg-teal-50 disabled:cursor-not-allowed disabled:opacity-60"
              :disabled="saving"
              type="button"
              @click="evidenceInput?.click()"
            >
              <Loader2 v-if="saving" class="h-5 w-5 animate-spin text-teal-700" />
              <ImagePlus v-else class="h-5 w-5 text-teal-700" />
              <span class="mt-2 text-sm font-medium text-slate-800">{{ evidenceDragging ? "松开上传" : "点击或拖拽上传佐证材料（可多选）" }}</span>
            </button>
          </div>
        </div>

        <div class="space-y-3 bg-white p-5">
          <div class="flex items-center justify-between"><span class="field-label">上传发票</span><span class="text-xs text-slate-500">可多选，OCR 自动识别多张</span></div>
          <div
            class="upload-zone min-h-28 w-full border border-dashed transition"
            :class="invoiceDragging ? 'border-teal-600 bg-teal-50' : 'border-slate-300 bg-slate-50'"
            @dragenter.prevent="invoiceDragging = true"
            @dragover.prevent="invoiceDragging = true"
            @dragleave.prevent="invoiceDragging = false"
            @drop.prevent="handleInvoiceDrop"
          >
            <div v-if="displayInvoiceAttachments.length" class="grid grid-cols-2 gap-2 p-3 sm:grid-cols-3">
              <UploadAttachmentTile
                v-for="attachment in displayInvoiceAttachments"
                :key="attachment.id"
                :attachment="attachment"
                :removable="canRemoveInvoice && !saving"
                :removing="removingAttachmentId === attachment.id"
                @preview="openAttachmentPreview"
                @remove="removeInvoiceAttachment"
              />
              <button
                class="flex aspect-square flex-col items-center justify-center rounded-lg border border-dashed border-slate-300 bg-white text-slate-500 transition hover:border-teal-600 hover:bg-teal-50 hover:text-teal-700 disabled:cursor-not-allowed disabled:opacity-60"
                :disabled="invoiceUploadLocked"
                type="button"
                @click="invoiceInput?.click()"
              >
                <Loader2 v-if="saving" class="h-5 w-5 animate-spin" />
                <FilePlus2 v-else class="h-5 w-5" />
                <span class="mt-1 text-[11px] font-medium">继续上传</span>
              </button>
            </div>
            <button
              v-else
              class="flex min-h-28 w-full flex-col items-center justify-center px-4 text-center transition hover:bg-teal-50 disabled:cursor-not-allowed disabled:opacity-60"
              :disabled="invoiceUploadLocked"
              type="button"
              @click="invoiceInput?.click()"
            >
              <Loader2 v-if="saving" class="h-5 w-5 animate-spin text-teal-700" />
              <FilePlus2 v-else class="h-5 w-5 text-teal-700" />
              <span class="mt-2 text-sm font-medium text-slate-800">{{ invoiceDragging ? "松开上传" : "点击或拖拽上传发票（可多选）" }}</span>
            </button>
          </div>
          <div v-if="displayInvoiceItems.length" class="space-y-2">
            <div class="flex items-center justify-between border-l-2 border-teal-600 bg-teal-50 px-3 py-2 text-xs">
              <span class="text-teal-800">已识别 {{ displayInvoiceItems.length }} 张发票</span>
              <strong class="text-teal-950">合计 {{ formatCurrency(linkedInvoiceAmount) }}</strong>
            </div>
            <div
              v-for="invoice in displayInvoiceItems"
              :key="`${invoice.attachment_id}-${invoice.invoice_item_index}`"
              class="grid grid-cols-2 gap-x-4 gap-y-1.5 bg-slate-50 px-3 py-2 text-xs text-slate-500"
            >
              <span>发票号码</span><strong class="truncate text-right text-slate-900">{{ invoiceText(invoice.item, ["invoice_number", "number"]) }}</strong>
              <span>金额</span><strong class="text-right text-slate-900">{{ formatCurrency(Number(invoice.item.amount)) }}</strong>
              <span>销售方</span><strong class="truncate text-right text-slate-900">{{ invoiceText(invoice.item, ["seller", "seller_name"]) }}</strong>
            </div>
          </div>
        </div>
      </div>

      <AttachmentPreviewModal :attachment="previewAttachment" :open="Boolean(previewAttachment)" @close="closeAttachmentPreview" />

      <div class="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 px-5 py-4">
        <p class="text-xs text-slate-500">
          {{
            targetExpense?.reject_reason
              ? "修改材料或发票后重新提交。"
              : isEditingPendingExpense
                ? "补齐发票后即可提交这笔报销。"
                : "没有发票也可以先保存，记录会显示为待补材料。"
          }}
        </p>
        <div class="flex flex-wrap items-center gap-2">
          <button class="secondary-button h-9 px-3 text-xs" type="button" @click="isComposerOpen = false">收起</button>
          <button v-if="!isEditingPendingExpense" class="secondary-button h-9 px-3 text-xs" :disabled="saving" type="button" @click="saveDraft">保存待补</button>
          <button class="primary-button h-9 px-3 text-xs" :disabled="saving || (isEditingPendingExpense ? !canSubmitExisting : !canSubmitNew)" type="button" @click="submitCurrent">
            <Loader2 v-if="saving" class="h-3.5 w-3.5 animate-spin" />
            <CheckCircle2 v-else class="h-3.5 w-3.5" /> 提交报销
          </button>
        </div>
      </div>
    </section>

    <section>
      <div class="mb-3 flex items-center justify-between"><h2 class="section-title">本月记录</h2><span class="text-xs text-slate-500">{{ currentMonthExpenses.length }} 笔</span></div>
      <div v-if="loading" class="border-y border-slate-200 bg-white px-4 py-10 text-center text-sm text-slate-500">加载中...</div>
      <div v-else-if="!currentMonthExpenses.length" class="border-y border-slate-200 bg-white px-4 py-12 text-center text-sm text-slate-500">本月还没有报销记录，先新建一笔。</div>
      <div v-else class="overflow-x-auto border-y border-slate-200 bg-white">
        <table class="min-w-[900px] w-full text-left text-[13px]">
          <thead class="border-b border-slate-200 bg-slate-50 text-xs font-medium text-slate-500">
            <tr>
              <th class="px-4 py-2.5">状态</th>
              <th class="px-4 py-2.5">报销事项</th>
              <th class="px-4 py-2.5">类别</th>
              <th class="px-4 py-2.5 text-right">金额</th>
              <th class="px-4 py-2.5">替票</th>
              <th class="px-4 py-2.5">佐证</th>
              <th class="px-4 py-2.5">发票</th>
              <th class="px-4 py-2.5 text-right">操作</th>
            </tr>
          </thead>
          <tbody
            v-for="section in tableSections"
            :key="section.key"
            class="divide-y divide-slate-100"
            :class="tableSectionClass(section.key)"
          >
            <tr v-for="record in section.records" :key="record.id" class="h-14 transition" :class="tableRowClass(section.key, record)">
              <td class="px-4 py-2">
                <span class="status-pill" :class="recordStateClass(record)">{{ recordStateLabel(record) }}</span>
                <div v-if="record.reject_reason" class="mt-1 max-w-40 truncate text-[11px] text-rose-600" :title="record.reject_reason">
                  {{ record.reject_reason }}
                </div>
              </td>
              <td class="px-4 py-2 font-medium" :class="section.key === 'approved' ? 'text-slate-500' : 'text-ink'">{{ record.project_name || record.category }}</td>
              <td class="px-4 py-2 text-slate-600">{{ record.category }}</td>
              <td class="px-4 py-2 text-right font-medium" :class="section.key === 'approved' ? 'text-slate-500' : 'text-ink'">{{ formatCurrency(record.actual_amount) }}</td>
              <td class="px-4 py-2"><span :class="record.is_substitute ? 'text-orange-700' : 'text-slate-500'">{{ record.is_substitute ? "是" : "否" }}</span></td>
              <td class="px-4 py-2"><span :class="record.attachments.length ? 'text-slate-700' : 'text-amber-700'">{{ record.attachments.length ? `${record.attachments.length} 份` : "未上传" }}</span></td>
              <td class="px-4 py-2"><span :class="record.allocation_count ? 'text-teal-700' : 'text-amber-700'">{{ record.allocation_count ? "已上传" : "未上传" }}</span></td>
              <td class="px-4 py-2 text-right">
                <div class="flex items-center justify-end gap-1.5">
                  <template v-if="recordState(record) === 'rejected'">
                    <button class="secondary-button h-8 px-2.5 text-xs" type="button" @click="openExistingExpense(record)">修改</button>
                    <button
                      v-if="record.allocation_count && record.remaining_amount <= 0"
                      class="primary-button h-8 px-2.5 text-xs"
                      :disabled="saving"
                      type="button"
                      @click="submitRecord(record)"
                    >
                      重新提交
                    </button>
                  </template>
                  <template v-else-if="recordState(record) === 'missing_material'">
                    <button class="secondary-button h-8 px-2.5 text-xs" type="button" @click="openExistingExpense(record)">补材料</button>
                    <button class="secondary-button h-8 px-2.5 text-xs text-rose-700 hover:bg-rose-50" type="button" :disabled="saving" @click="deleteRecord(record)">删除</button>
                  </template>
                  <button v-else-if="recordState(record) === 'ready'" class="primary-button h-8 px-2.5 text-xs" :disabled="saving" type="button" @click="submitRecord(record)">提交报销</button>
                  <button v-else-if="recordState(record) === 'submitted'" class="secondary-button h-8 px-2.5 text-xs" :disabled="saving" type="button" @click="withdraw(record)">撤回</button>
                  <span v-else class="text-xs text-slate-400">—</span>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>
