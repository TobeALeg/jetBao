<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { AlertTriangle, CheckCircle2, ImagePlus, Link2, Loader2, PlusCircle, ReceiptText, Trash2, X } from "lucide-vue-next";
import AttachmentThumb from "../components/AttachmentThumb.vue";
import InvoiceUploadPanel from "../components/InvoiceUploadPanel.vue";
import { buyerMatchStatus, isDifferentAllowedBuyer } from "../constants/companyEntities";
import { DEFAULT_EXPENSE_CATEGORY, EXPENSE_CATEGORIES } from "../constants/expenseCategories";
import {
  addAttachmentsToInvoicePool,
  createExpenseAllocationsBatch,
  createExpenseDraft,
  deleteAttachment,
  deleteExpense,
  deleteExpenseAttachment,
  linkExpenseAttachments,
  listExpenses,
  listInvoicePool,
  uploadAttachments
} from "../services/api";
import { currentReimbursementMonth, formatCurrency, formatDate } from "../utils/format";
import type { Attachment, DraftExpenseCreatePayload, Expense, InvoicePoolItem, User } from "../types";

const props = defineProps<{
  user: User;
  draftExpense?: Expense | null;
}>();

const emit = defineEmits<{
  submitted: [];
}>();

const expenses = ref<Expense[]>([]);
const invoicePool = ref<InvoicePoolItem[]>([]);
const uploadedAttachments = ref<Attachment[]>([]);
const loading = ref(false);
const savingExpense = ref(false);
const recordingItem = ref(false);
const matching = ref(false);
const poolingInvoices = ref(false);
const error = ref("");
const success = ref("");
const transactionInputRef = ref<HTMLInputElement | null>(null);
const transactionTargetExpenseId = ref<number | null>(null);
const transactionUploadingExpenseId = ref<number | null>(null);
const deletingExpenseId = ref<number | null>(null);
const deletingAttachmentId = ref<number | null>(null);
const deletingExpenseAttachmentKey = ref("");

const selectedExpenseId = ref<number | null>(props.draftExpense?.id ?? null);
const selectedInvoiceKeys = ref<string[]>([]);
const allocationNote = ref("");

const expenseForm = reactive({
  project_name: "",
  actual_amount: "",
  expense_month: currentReimbursementMonth(),
  category: DEFAULT_EXPENSE_CATEGORY
});

type StagedInvoiceReference = {
  attachment_id: number;
  invoice_item_index: number;
  invoice_amount: number;
  invoice_buyer: string;
};

const selectedExpense = computed(() => expenses.value.find((item) => item.id === selectedExpenseId.value) ?? null);
const selectedInvoices = computed(() => invoicePool.value.filter((item) => selectedInvoiceKeys.value.includes(invoiceKey(item))));
const selectedInvoiceTotal = computed(() => selectedInvoices.value.reduce((sum, item) => sum + Number(item.invoice_amount), 0));
const stagedInvoices = computed(() => stagedInvoiceRefs(uploadedAttachments.value));
const stagedInvoiceTotal = computed(() => roundCurrency(stagedInvoices.value.reduce((sum, invoice) => sum + invoice.invoice_amount, 0)));
const formActualAmount = computed(() => roundCurrency(Number(expenseForm.actual_amount) || 0));
const pendingExpenses = computed(() => expenses.value.filter((item) => item.remaining_amount > 0 || item.status === "draft"));
const usableInvoices = computed(() => invoicePool.value.filter((item) => item.remaining_amount > 0));

const isFormMode = computed(() => !selectedExpense.value);
const combinedInvoiceTotal = computed(() => roundCurrency(stagedInvoiceTotal.value + selectedInvoiceTotal.value));
const combinedInvoiceCount = computed(() => stagedInvoices.value.length + selectedInvoices.value.length);
const workBarTarget = computed(() => (isFormMode.value ? formActualAmount.value : Number(selectedExpense.value?.actual_amount ?? 0)));
const workBarDifference = computed(() => roundCurrency(combinedInvoiceTotal.value - workBarTarget.value));
const needsWorkBarNote = computed(() => workBarDifference.value > 0);
const workBarProgress = computed(() => {
  const target = workBarTarget.value;
  if (target <= 0) return 0;
  return Math.min((combinedInvoiceTotal.value / target) * 100, 100);
});
const workBarReady = computed(() => {
  if (matching.value || recordingItem.value || savingExpense.value) return false;
  if (workBarTarget.value <= 0) return false;
  if (combinedInvoiceTotal.value < workBarTarget.value) return false;
  if (needsWorkBarNote.value && !allocationNote.value.trim()) return false;
  if (isFormMode.value) return Boolean(expenseForm.project_name.trim()) && stagedInvoiceTotal.value > 0;
  return true;
});
const workBarActionLabel = computed(() => {
  if (matching.value || recordingItem.value) return "处理中";
  if (workBarTarget.value <= 0) return isFormMode.value ? "填写花费" : "等待花费";
  if (combinedInvoiceTotal.value <= 0) return "等待发票";
  if (workBarDifference.value < 0) return "还差";
  if (needsWorkBarNote.value && !allocationNote.value.trim()) return "填说明";
  if (needsWorkBarNote.value) return "替票记录";
  if (isFormMode.value) return "记录该笔";
  if (workBarDifference.value < 0) return "部分匹配";
  return "完成匹配";
});
const workBarTone = computed(() => {
  if (workBarTarget.value <= 0 || combinedInvoiceTotal.value <= 0) return "idle";
  if (workBarDifference.value < 0) return "waiting";
  if (needsWorkBarNote.value) return "substitute";
  if (workBarReady.value) return "ready";
  return "idle";
});

function invoiceKey(item: InvoicePoolItem): string {
  return `${item.attachment_id}:${item.invoice_item_index}`;
}

function statusLabel(expense: Expense): string {
  if (expense.status === "submitted") return "已提交";
  if (expense.allocated_amount > 0) return "部分匹配";
  return "待补票";
}

function invoiceStatusLabel(invoice: InvoicePoolItem): string {
  if (invoice.remaining_amount <= 0 || invoice.allocated_amount > 0) return "已匹配";
  return "待匹配";
}

function selectExpense(expense: Expense) {
  selectedExpenseId.value = expense.id;
}

function selectInvoice(invoice: InvoicePoolItem) {
  const key = invoiceKey(invoice);
  selectedInvoiceKeys.value = selectedInvoiceKeys.value.includes(key)
    ? selectedInvoiceKeys.value.filter((item) => item !== key)
    : [...selectedInvoiceKeys.value, key];
}

function removeSelectedInvoice(key: string) {
  selectedInvoiceKeys.value = selectedInvoiceKeys.value.filter((item) => item !== key);
}

function roundCurrency(value: number): number {
  return Math.round(value * 100) / 100;
}

function invoiceKeysForAttachmentIds(attachmentIds: number[]): string[] {
  const idSet = new Set(attachmentIds);
  return invoicePool.value.filter((item) => idSet.has(item.attachment_id) && item.remaining_amount > 0).map(invoiceKey);
}

function invoiceItemsOfAttachment(attachment: Attachment): Array<Record<string, unknown>> {
  const items = attachment.ocr_result.invoice_items;
  return Array.isArray(items) ? (items as Array<Record<string, unknown>>) : [];
}

function stagedInvoiceRefs(attachments: Attachment[]): StagedInvoiceReference[] {
  return attachments.flatMap((attachment) =>
    invoiceItemsOfAttachment(attachment)
      .map((item, index) => ({ item, index }))
      .filter(({ item }) => typeof item.amount === "number" && item.amount > 0)
      .map(({ item, index }) => ({
        attachment_id: attachment.id,
        invoice_item_index: index,
        invoice_amount: Number(item.amount),
        invoice_buyer: typeof item.buyer === "string" ? item.buyer : ""
      }))
  );
}

function invoiceBuyerStatusLabel(buyer: string): string {
  if (!buyer) return "未识别抬头";
  const status = buyerMatchStatus(buyer);
  if (status === "partial") return `${buyer}（需确认）`;
  if (status === "none") return `${buyer}（不可用）`;
  return isDifferentAllowedBuyer(buyer, props.user.company_entity) ? `${buyer}（可用抬头）` : buyer;
}

function invoiceBuyerTone(buyer: string): "ok" | "warn" | "danger" {
  const status = buyerMatchStatus(buyer);
  if (status === "exact" && !isDifferentAllowedBuyer(buyer, props.user.company_entity)) return "ok";
  if (status === "exact" || status === "partial") return "warn";
  return "danger";
}

function needsBuyerConfirmation(invoices: Array<{ invoice_buyer: string }>): boolean {
  return invoices.some((invoice) => buyerMatchStatus(invoice.invoice_buyer) === "partial");
}

function clearUploadedAttachments(attachments: Attachment[]) {
  const clearedIds = new Set(attachments.map((attachment) => attachment.id));
  attachments.forEach((attachment) => {
    if (attachment.preview_url) URL.revokeObjectURL(attachment.preview_url);
  });
  uploadedAttachments.value = uploadedAttachments.value.filter((attachment) => !clearedIds.has(attachment.id));
}

function attachmentDeleteKey(expenseId: number, attachmentId: number): string {
  return `${expenseId}:${attachmentId}`;
}

function isTransactionImageFile(file: File): boolean {
  return file.type.startsWith("image/") || /\.(png|jpe?g|webp|gif|bmp)$/i.test(file.name);
}

function triggerTransactionUpload(expense: Expense) {
  selectedExpenseId.value = expense.id;
  transactionTargetExpenseId.value = expense.id;
  transactionInputRef.value?.click();
}

async function loadWorkspace() {
  loading.value = true;
  error.value = "";
  try {
    const [expenseRows, invoiceRows] = await Promise.all([listExpenses(), listInvoicePool()]);
    expenses.value = expenseRows;
    invoicePool.value = invoiceRows;
    if (props.draftExpense && !selectedExpenseId.value) {
      selectedExpenseId.value = props.draftExpense.id;
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : "加载失败";
  } finally {
    loading.value = false;
  }
}

async function handleTransactionFiles(event: Event) {
  const input = event.target as HTMLInputElement;
  const expenseId = transactionTargetExpenseId.value;
  const files = Array.from(input.files ?? []).filter(isTransactionImageFile);
  input.value = "";

  if (!expenseId) return;
  if (!files.length) {
    error.value = "请上传交易记录图片。";
    return;
  }

  transactionUploadingExpenseId.value = expenseId;
  error.value = "";
  success.value = "";
  try {
    const attachments = await uploadAttachments(files);
    await linkExpenseAttachments(expenseId, { attachment_ids: attachments.map((item) => item.id) });
    await loadWorkspace();
    selectedExpenseId.value = expenseId;
    success.value = "交易记录已保存到花费项目";
  } catch (err) {
    error.value = err instanceof Error ? err.message : "交易记录上传失败";
  } finally {
    transactionUploadingExpenseId.value = null;
    transactionTargetExpenseId.value = null;
  }
}

function expensePayloadFromForm(): DraftExpenseCreatePayload | null {
  const data = {
    project_name: expenseForm.project_name.trim(),
    actual_amount: Number(expenseForm.actual_amount),
    expense_month: expenseForm.expense_month,
    category: expenseForm.category
  };
  if (!data.project_name) {
    error.value = "请填写项目名称。";
    return null;
  }
  if (!data.actual_amount || data.actual_amount <= 0) {
    error.value = "请填写金额。";
    return null;
  }
  return data;
}

function resetExpenseForm() {
  expenseForm.project_name = "";
  expenseForm.actual_amount = "";
  expenseForm.category = DEFAULT_EXPENSE_CATEGORY;
}

async function submitExpense(payload?: DraftExpenseCreatePayload) {
  const data = payload ?? expensePayloadFromForm();
  if (!data) return;

  savingExpense.value = true;
  error.value = "";
  success.value = "";
  try {
    const created = await createExpenseDraft(data);
    resetExpenseForm();
    await loadWorkspace();
    selectedExpenseId.value = created.id;
    success.value = "花费项目已加入待定池";
  } catch (err) {
    error.value = err instanceof Error ? err.message : "保存失败";
  } finally {
    savingExpense.value = false;
  }
}

async function handleUploaded(attachments: Attachment[]) {
  if (!attachments.length) return;
  error.value = "";
  uploadedAttachments.value = [...attachments, ...uploadedAttachments.value];
  success.value = "发票已解析，可加入发票池或随当前花费一起记录";
}

async function addUploadedInvoicesToPool() {
  const stagedAttachments = [...uploadedAttachments.value];
  if (!stagedAttachments.length) {
    error.value = "请先上传发票。";
    return;
  }
  if (!stagedInvoiceRefs(stagedAttachments).length) {
    error.value = "未识别到可加入发票池的票据条目。";
    return;
  }

  poolingInvoices.value = true;
  error.value = "";
  success.value = "";
  try {
    await addAttachmentsToInvoicePool(stagedAttachments.map((attachment) => attachment.id));
    await loadWorkspace();
    selectedInvoiceKeys.value = invoiceKeysForAttachmentIds(stagedAttachments.map((attachment) => attachment.id));
    clearUploadedAttachments(stagedAttachments);
    success.value = "发票已加入发票池";
  } catch (err) {
    error.value = err instanceof Error ? err.message : "加入发票池失败";
  } finally {
    poolingInvoices.value = false;
  }
}

async function removeUploaded(id: number) {
  if (!window.confirm("删除这份刚上传的发票文件吗？")) return;
  deletingAttachmentId.value = id;
  error.value = "";
  success.value = "";
  try {
    await deleteAttachment(id);
    const removed = uploadedAttachments.value.find((item) => item.id === id);
    if (removed?.preview_url) URL.revokeObjectURL(removed.preview_url);
    uploadedAttachments.value = uploadedAttachments.value.filter((item) => item.id !== id);
    selectedInvoiceKeys.value = selectedInvoiceKeys.value.filter((key) => !key.startsWith(`${id}:`));
    await loadWorkspace();
    success.value = "发票文件已删除";
  } catch (err) {
    error.value = err instanceof Error ? err.message : "删除发票失败";
  } finally {
    deletingAttachmentId.value = null;
  }
}

async function deleteExpenseRecord(expense: Expense) {
  if (!window.confirm(`删除花费记录「${expense.project_name || expense.category}」吗？`)) return;
  deletingExpenseId.value = expense.id;
  error.value = "";
  success.value = "";
  try {
    await deleteExpense(expense.id);
    if (selectedExpenseId.value === expense.id) selectedExpenseId.value = null;
    selectedInvoiceKeys.value = [];
    await loadWorkspace();
    success.value = "花费记录已删除";
  } catch (err) {
    error.value = err instanceof Error ? err.message : "删除花费记录失败";
  } finally {
    deletingExpenseId.value = null;
  }
}

async function deleteInvoiceFile(invoice: InvoicePoolItem) {
  if (!window.confirm(`删除发票「${invoice.attachment_name}」吗？`)) return;
  deletingAttachmentId.value = invoice.attachment_id;
  error.value = "";
  success.value = "";
  try {
    await deleteAttachment(invoice.attachment_id);
    selectedInvoiceKeys.value = selectedInvoiceKeys.value.filter((key) => !key.startsWith(`${invoice.attachment_id}:`));
    const removed = uploadedAttachments.value.find((item) => item.id === invoice.attachment_id);
    if (removed?.preview_url) URL.revokeObjectURL(removed.preview_url);
    uploadedAttachments.value = uploadedAttachments.value.filter((item) => item.id !== invoice.attachment_id);
    await loadWorkspace();
    success.value = "发票文件已删除";
  } catch (err) {
    error.value = err instanceof Error ? err.message : "删除发票失败";
  } finally {
    deletingAttachmentId.value = null;
  }
}

async function deleteTransactionAttachment(expense: Expense, attachment: Attachment) {
  if (!window.confirm(`删除交易记录「${attachment.original_filename}」吗？`)) return;
  const key = attachmentDeleteKey(expense.id, attachment.id);
  deletingExpenseAttachmentKey.value = key;
  error.value = "";
  success.value = "";
  try {
    const updated = await deleteExpenseAttachment(expense.id, attachment.id);
    expenses.value = expenses.value.map((item) => (item.id === updated.id ? updated : item));
    selectedExpenseId.value = expense.id;
    success.value = "交易记录已删除";
  } catch (err) {
    error.value = err instanceof Error ? err.message : "删除交易记录失败";
  } finally {
    deletingExpenseAttachmentKey.value = "";
  }
}

async function performWorkBarAction() {
  if (!workBarReady.value) return;

  const isSubstitute = needsWorkBarNote.value;
  const note = isSubstitute ? allocationNote.value.trim() : "";

  const stagedAttachments = [...uploadedAttachments.value];
  const invoiceRefs = [
    ...stagedInvoiceRefs(stagedAttachments),
    ...selectedInvoices.value.map((invoice) => ({
      attachment_id: invoice.attachment_id,
      invoice_item_index: invoice.invoice_item_index,
      invoice_amount: Number(invoice.invoice_amount),
      invoice_buyer: invoice.invoice_buyer
    }))
  ];

  if (!invoiceRefs.length) {
    error.value = "请先上传发票或从发票池选择发票。";
    return;
  }

  const buyerConfirmed = needsBuyerConfirmation(invoiceRefs);
  if (buyerConfirmed && !window.confirm("有发票抬头仅部分命中公司主体，请人工确认抬头无误后继续。")) {
    return;
  }

  recordingItem.value = true;
  matching.value = true;
  error.value = "";
  success.value = "";
  let createdExpenseId: number | null = null;

  try {
    let expenseId: number;

    if (isFormMode.value) {
      const data = expensePayloadFromForm();
      if (!data) {
        recordingItem.value = false;
        matching.value = false;
        return;
      }
      const created = await createExpenseDraft(data);
      createdExpenseId = created.id;
      expenseId = created.id;
      resetExpenseForm();
    } else {
      expenseId = selectedExpense.value!.id;
    }

    const updated = await createExpenseAllocationsBatch({
      expense_id: expenseId,
      invoices: invoiceRefs.map((invoice) => ({
        attachment_id: invoice.attachment_id,
        invoice_item_index: invoice.invoice_item_index
      })),
      note: isSubstitute ? note : "",
      buyer_confirmed: buyerConfirmed
    });

    await loadWorkspace();
    selectedExpenseId.value = updated.remaining_amount > 0 ? updated.id : null;
    selectedInvoiceKeys.value = [];
    allocationNote.value = "";
    clearUploadedAttachments(stagedAttachments);

    success.value = isSubstitute ? "已记录该笔并标记为替票" : "已记录该笔并绑定发票";
    if (updated.remaining_amount <= 0) emit("submitted");
  } catch (err) {
    const message = err instanceof Error ? err.message : "操作失败";
    error.value = createdExpenseId ? `花费已创建，绑定失败：${message}` : message;
    if (createdExpenseId) {
      await loadWorkspace();
      selectedExpenseId.value = createdExpenseId;
    }
  } finally {
    matching.value = false;
    recordingItem.value = false;
  }
}

watch(
  () => props.draftExpense?.id,
  (id) => {
    if (!id) return;
    selectedExpenseId.value = id;
    loadWorkspace();
  }
);

onMounted(loadWorkspace);
</script>

<template>
  <div class="mx-auto max-w-7xl space-y-5">
    <div>
      <h1 class="page-title">报销整理工作台</h1>
      <p class="muted mt-1">填写花费并上传发票，或从下方池中选择后匹配。</p>
    </div>

    <p v-if="error" class="rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-700">{{ error }}</p>
    <p v-if="success" class="rounded-md bg-teal-50 px-3 py-2 text-sm text-teal-800">{{ success }}</p>

    <!-- 工作栏：统一录入与匹配 -->
    <section class="tool-panel overflow-hidden rounded-lg">
      <div class="intake-grid">
        <!-- 左侧：花费输入 / 已选花费 + 替票说明 -->
        <div class="work-bar-panel">
          <div class="flex items-center justify-between gap-3">
            <div class="text-xs font-semibold uppercase tracking-normal text-slate-400">花费</div>
            <button
              v-if="selectedExpense"
              class="text-xs text-slate-500 transition hover:text-rose-600"
              type="button"
              @click="selectedExpenseId = null; selectedInvoiceKeys = []; allocationNote = ''"
            >
              取消选择
            </button>
          </div>

          <div v-if="selectedExpense" class="mt-4 space-y-4">
            <div>
              <div class="truncate text-lg font-semibold text-ink">{{ selectedExpense.project_name || selectedExpense.category }}</div>
              <div class="mt-1 flex items-center gap-2 text-xs text-slate-500">
                <span>{{ selectedExpense.expense_month }}</span>
                <span class="status-pill bg-slate-100 text-slate-600">{{ selectedExpense.category }}</span>
              </div>
            </div>
            <div class="grid grid-cols-3 gap-2 text-xs">
              <div class="match-mini-stat">
                <span>花费</span>
                <strong>{{ formatCurrency(selectedExpense.actual_amount) }}</strong>
              </div>
              <div class="match-mini-stat">
                <span>已匹配</span>
                <strong>{{ formatCurrency(selectedExpense.allocated_amount) }}</strong>
              </div>
              <div class="match-mini-stat">
                <span>待匹配</span>
                <strong>{{ formatCurrency(selectedExpense.remaining_amount) }}</strong>
              </div>
            </div>
            <div v-if="selectedExpense.attachments.length" class="flex flex-wrap gap-2">
              <div
                v-for="attachment in selectedExpense.attachments.slice(0, 3)"
                :key="attachment.id"
                class="inline-flex max-w-full items-center gap-1.5 rounded-md bg-slate-100 px-2 py-1 text-xs text-slate-600"
              >
                <AttachmentThumb :attachment="attachment" />
                <span class="truncate">{{ attachment.original_filename }}</span>
                <button
                  class="grid h-6 w-6 shrink-0 place-items-center rounded text-slate-400 transition hover:bg-rose-50 hover:text-rose-700"
                  type="button"
                  :disabled="deletingExpenseAttachmentKey === attachmentDeleteKey(selectedExpense.id, attachment.id)"
                  :title="`删除 ${attachment.original_filename}`"
                  @click="deleteTransactionAttachment(selectedExpense, attachment)"
                >
                  <Loader2
                    v-if="deletingExpenseAttachmentKey === attachmentDeleteKey(selectedExpense.id, attachment.id)"
                    class="h-3.5 w-3.5 animate-spin"
                  />
                  <X v-else class="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
            <button
              class="secondary-button h-9 px-3"
              type="button"
              :disabled="transactionUploadingExpenseId === selectedExpense.id"
              @click="triggerTransactionUpload(selectedExpense)"
            >
              <Loader2 v-if="transactionUploadingExpenseId === selectedExpense.id" class="h-4 w-4 animate-spin" />
              <ImagePlus v-else class="h-4 w-4" />
              {{ transactionUploadingExpenseId === selectedExpense.id ? "上传中" : "上传附件" }}
            </button>
          </div>

          <form v-else class="mt-4 space-y-3" @submit.prevent="submitExpense()">
            <div>
              <label class="field-label" for="expense-project">项目名称</label>
              <input id="expense-project" v-model="expenseForm.project_name" class="field-input mt-1" placeholder="如：客户拜访打车" />
            </div>
            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="field-label" for="expense-amount">金额</label>
                <input id="expense-amount" v-model="expenseForm.actual_amount" class="field-input mt-1" inputmode="decimal" />
              </div>
              <div>
                <label class="field-label" for="expense-category">类别</label>
                <select id="expense-category" v-model="expenseForm.category" class="field-input mt-1">
                  <option v-for="category in EXPENSE_CATEGORIES" :key="category">{{ category }}</option>
                </select>
              </div>
            </div>
            <div class="flex items-center gap-2 text-xs text-slate-500">
              <span>月份：{{ expenseForm.expense_month }}</span>
            </div>
            <button
              class="secondary-button w-full justify-center"
              type="submit"
              :disabled="savingExpense || !expenseForm.project_name.trim() || formActualAmount <= 0"
            >
              <PlusCircle class="h-4 w-4" />
              {{ savingExpense ? "正在加入..." : "加入花费池" }}
            </button>
          </form>

          <div v-if="needsWorkBarNote" class="mt-4 space-y-1 border-t border-slate-200 pt-4">
            <label class="field-label" for="workbar-note">替票说明</label>
            <textarea
              id="workbar-note"
              v-model="allocationNote"
              class="field-textarea mt-1 min-h-14"
              rows="2"
              placeholder="说明为什么使用大额发票替票"
            />
            <p class="text-xs text-amber-700">票面合计超过花费金额，保存后会标记为替票。</p>
          </div>
        </div>

        <!-- 中间：动作按钮 -->
        <div class="record-connector" :data-tone="workBarTone">
          <button
            class="record-link-button"
            type="button"
            :data-tone="workBarTone"
            :disabled="!workBarReady"
            @click="performWorkBarAction"
          >
            <Loader2 v-if="matching || recordingItem" class="h-5 w-5 animate-spin" />
            <Link2 v-else class="h-5 w-5" />
            <span>{{ workBarActionLabel }}</span>
          </button>
          <div v-if="combinedInvoiceCount > 0 || workBarTarget > 0" class="record-link-caption">
            <span v-if="workBarDifference > 0" class="text-amber-700">超出 {{ formatCurrency(workBarDifference) }}</span>
            <span v-else-if="workBarDifference < 0">还差 {{ formatCurrency(Math.abs(workBarDifference)) }}</span>
            <span v-else-if="workBarTarget > 0 && combinedInvoiceTotal > 0" class="text-teal-700">刚好匹配</span>
          </div>
        </div>

        <!-- 右侧：发票上传 + 已选发票 -->
        <div class="work-bar-panel">
          <div class="text-xs font-semibold uppercase tracking-normal text-slate-400">发票</div>

          <div class="mt-4">
            <InvoiceUploadPanel
              :attachments="uploadedAttachments"
              :current-company="user.company_entity"
              :removing-id="deletingAttachmentId"
              :pooling="poolingInvoices"
              @uploaded="handleUploaded"
              @add-to-pool="addUploadedInvoicesToPool"
              @remove="removeUploaded"
            />
          </div>

          <div v-if="selectedInvoices.length" class="mt-4">
            <div class="flex items-center justify-between">
              <div class="text-xs font-medium text-slate-500">从发票池已选 {{ selectedInvoices.length }} 张</div>
              <span class="status-pill bg-teal-50 text-teal-700">{{ formatCurrency(selectedInvoiceTotal) }}</span>
            </div>
            <div class="mt-2 space-y-2">
              <div
                v-for="invoice in selectedInvoices"
                :key="invoiceKey(invoice)"
                class="match-invoice-row"
              >
                <div class="min-w-0">
                  <div class="truncate text-sm font-medium text-ink">{{ invoice.invoice_type }}</div>
                  <div class="mt-0.5 truncate text-xs text-slate-500">{{ invoice.attachment_name }}</div>
                </div>
                <div class="flex shrink-0 items-center gap-2">
                  <span class="text-sm font-semibold text-ink">{{ formatCurrency(invoice.invoice_amount) }}</span>
                  <button
                    class="grid h-7 w-7 place-items-center rounded-md text-slate-400 transition hover:bg-rose-50 hover:text-rose-700"
                    type="button"
                    :aria-label="`移除 ${invoice.invoice_type}`"
                    @click="removeSelectedInvoice(invoiceKey(invoice))"
                  >
                    <X class="h-4 w-4" />
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <input
      ref="transactionInputRef"
      class="hidden"
      type="file"
      accept="image/*"
      multiple
      @change="handleTransactionFiles"
    />

    <!-- 待定池：花费卡片 ‖ 发票卡片 -->
    <div class="grid gap-5 xl:grid-cols-2">
      <section class="tool-panel rounded-lg">
        <div class="border-b border-slate-200 px-5 py-4">
          <h2 class="section-title">花费池</h2>
          <p class="muted mt-1">点击选中后在工作栏关联发票。</p>
        </div>

        <div v-if="loading" class="px-5 py-10 text-center text-sm text-slate-500">正在加载...</div>
        <div v-else-if="!pendingExpenses.length" class="empty-state">
          <div class="empty-state-icon">
            <PlusCircle class="h-6 w-6" />
          </div>
          <div>
            <div class="text-sm font-medium text-slate-700">花费池为空</div>
            <div class="mt-1 text-xs text-slate-500">在工作栏填写项目名称和金额，将花费加入待定池。</div>
          </div>
        </div>
        <div v-else class="grid gap-3 p-5 sm:grid-cols-2">
          <article
            v-for="expense in pendingExpenses"
            :key="expense.id"
            class="flex cursor-pointer flex-col gap-3 rounded-lg border p-4 text-left transition hover:border-teal-300 hover:shadow-sm"
            :class="selectedExpenseId === expense.id ? 'border-teal-400 bg-teal-50/60 ring-2 ring-teal-700/10' : 'border-slate-200 bg-white'"
            tabindex="0"
            @click="selectExpense(expense)"
            @keydown.enter.prevent="selectExpense(expense)"
          >
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <div class="truncate text-sm font-semibold text-ink">{{ expense.project_name || expense.category }}</div>
                <div class="mt-1 text-xs text-slate-500">{{ expense.expense_month }} · {{ expense.category }}</div>
              </div>
              <div class="flex shrink-0 items-center gap-1">
                <span class="status-pill" :class="expense.status === 'submitted' ? 'bg-teal-50 text-teal-700' : 'bg-amber-50 text-amber-700'">
                  {{ statusLabel(expense) }}
                </span>
                <button
                  class="grid h-8 w-8 place-items-center rounded-md text-slate-400 transition hover:bg-rose-50 hover:text-rose-700 disabled:cursor-not-allowed disabled:text-slate-300"
                  type="button"
                  :disabled="deletingExpenseId === expense.id"
                  :title="`删除 ${expense.project_name || expense.category}`"
                  @click.stop="deleteExpenseRecord(expense)"
                >
                  <Loader2 v-if="deletingExpenseId === expense.id" class="h-4 w-4 animate-spin" />
                  <Trash2 v-else class="h-4 w-4" />
                </button>
              </div>
            </div>
            <div class="grid gap-1.5 text-xs text-slate-500">
              <div>金额：<span class="font-medium text-slate-800">{{ formatCurrency(expense.actual_amount) }}</span></div>
              <div>已匹配：<span class="font-medium text-slate-800">{{ formatCurrency(expense.allocated_amount) }}</span></div>
            </div>
            <div class="mt-auto flex flex-wrap items-center gap-2">
              <div
                v-for="attachment in expense.attachments.slice(0, 2)"
                :key="attachment.id"
                class="inline-flex max-w-full items-center gap-1.5 rounded-md bg-slate-100 px-2 py-1 text-xs text-slate-600"
              >
                <AttachmentThumb :attachment="attachment" />
                <span class="truncate">{{ attachment.original_filename }}</span>
                <button
                  class="grid h-6 w-6 shrink-0 place-items-center rounded text-slate-400 transition hover:bg-rose-50 hover:text-rose-700 disabled:cursor-not-allowed disabled:text-slate-300"
                  type="button"
                  :disabled="deletingExpenseAttachmentKey === attachmentDeleteKey(expense.id, attachment.id)"
                  :title="`删除 ${attachment.original_filename}`"
                  @click.stop="deleteTransactionAttachment(expense, attachment)"
                >
                  <Loader2
                    v-if="deletingExpenseAttachmentKey === attachmentDeleteKey(expense.id, attachment.id)"
                    class="h-3.5 w-3.5 animate-spin"
                  />
                  <X v-else class="h-3.5 w-3.5" />
                </button>
              </div>
              <button
                class="inline-flex h-8 items-center gap-1 rounded-md border border-slate-200 bg-white px-2 text-xs font-medium text-slate-700 transition hover:border-teal-600 hover:text-teal-700"
                type="button"
                :disabled="transactionUploadingExpenseId === expense.id"
                @click.stop="triggerTransactionUpload(expense)"
              >
                <Loader2 v-if="transactionUploadingExpenseId === expense.id" class="h-3.5 w-3.5 animate-spin" />
                <ImagePlus v-else class="h-3.5 w-3.5" />
                {{ transactionUploadingExpenseId === expense.id ? "上传中" : "交易记录" }}
              </button>
            </div>
          </article>
        </div>
      </section>

      <section class="tool-panel rounded-lg">
        <div class="border-b border-slate-200 px-5 py-4">
          <h2 class="section-title">发票池</h2>
          <p class="muted mt-1">点击可多选，同一张发票只能匹配一个花费。</p>
        </div>
        <div v-if="!usableInvoices.length" class="empty-state">
          <div class="empty-state-icon">
            <ReceiptText class="h-6 w-6" />
          </div>
          <div>
            <div class="text-sm font-medium text-slate-700">没有可用发票</div>
            <div class="mt-1 text-xs text-slate-500">先在工作栏的发票区域上传发票 PDF 或图片。</div>
          </div>
        </div>
        <div v-else class="grid gap-3 p-5 sm:grid-cols-2">
          <article
            v-for="invoice in usableInvoices"
            :key="invoiceKey(invoice)"
            class="flex cursor-pointer flex-col gap-3 rounded-lg border p-4 text-left transition hover:border-teal-300 hover:shadow-sm"
            :class="selectedInvoiceKeys.includes(invoiceKey(invoice)) ? 'border-teal-400 bg-teal-50/60 ring-2 ring-teal-700/10' : 'border-slate-200 bg-white'"
            tabindex="0"
            @click="selectInvoice(invoice)"
            @keydown.enter.prevent="selectInvoice(invoice)"
          >
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <div class="truncate text-sm font-semibold text-ink">{{ invoice.invoice_type }}</div>
                <div class="mt-1 truncate text-xs text-slate-500">{{ invoice.attachment_name }}</div>
              </div>
              <div class="flex shrink-0 items-center gap-1">
                <span class="status-pill" :class="invoice.allocated_amount ? 'bg-amber-50 text-amber-700' : 'bg-slate-100 text-slate-600'">
                  {{ invoiceStatusLabel(invoice) }}
                </span>
                <button
                  class="grid h-8 w-8 place-items-center rounded-md text-slate-400 transition hover:bg-rose-50 hover:text-rose-700 disabled:cursor-not-allowed disabled:text-slate-300"
                  type="button"
                  :disabled="deletingAttachmentId === invoice.attachment_id"
                  :title="`删除 ${invoice.attachment_name}`"
                  @click.stop="deleteInvoiceFile(invoice)"
                >
                  <Loader2 v-if="deletingAttachmentId === invoice.attachment_id" class="h-4 w-4 animate-spin" />
                  <Trash2 v-else class="h-4 w-4" />
                </button>
              </div>
            </div>
            <div class="grid gap-1.5 text-xs text-slate-500">
              <div>票面：<span class="font-medium text-slate-800">{{ formatCurrency(invoice.invoice_amount) }}</span></div>
              <div>可用：<span class="font-medium text-slate-800">{{ formatCurrency(invoice.remaining_amount) }}</span></div>
              <div>日期：<span class="font-medium text-slate-800">{{ invoice.invoice_date || formatDate(invoice.created_at) }}</span></div>
            </div>
            <div class="mt-auto flex items-center gap-2 text-xs text-slate-500">
              <ReceiptText class="h-3.5 w-3.5 shrink-0" />
              <span
                class="truncate"
                :class="{
                  'text-teal-700': invoiceBuyerTone(invoice.invoice_buyer) === 'ok',
                  'text-amber-700': invoiceBuyerTone(invoice.invoice_buyer) === 'warn',
                  'text-rose-700': invoiceBuyerTone(invoice.invoice_buyer) === 'danger'
                }"
              >
                {{ invoiceBuyerStatusLabel(invoice.invoice_buyer) }}
              </span>
              <CheckCircle2 v-if="invoiceBuyerTone(invoice.invoice_buyer) === 'ok'" class="h-3.5 w-3.5 shrink-0 text-teal-700" />
              <AlertTriangle v-else class="h-3.5 w-3.5 shrink-0" :class="invoiceBuyerTone(invoice.invoice_buyer) === 'warn' ? 'text-amber-600' : 'text-rose-600'" />
            </div>
          </article>
        </div>
      </section>
    </div>
  </div>
</template>
