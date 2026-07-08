<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import {
  ArrowRight, CheckCircle2, ImagePlus,
  Link2, Loader2, PlusCircle, ReceiptText, Trash2, X
} from "lucide-vue-next";
import AttachmentThumb from "../components/AttachmentThumb.vue";
import InvoiceUploadPanel from "../components/InvoiceUploadPanel.vue";
import { buyerMatchStatus, isDifferentAllowedBuyer } from "../constants/companyEntities";
import { DEFAULT_EXPENSE_CATEGORY, EXPENSE_CATEGORIES } from "../constants/expenseCategories";
import {
  addAttachmentsToInvoicePool,
  createAndSubmitExpense,
  createExpenseAllocationsBatch,
  createExpenseDraft,
  deleteAttachment,
  deleteExpense,
  deleteExpenseAttachment,
  linkExpenseAttachments,
  listExpenses,
  listInvoicePool,
  submitExpense,
  uploadAttachments,
  withdrawExpense,
} from "../services/api";
import { currentReimbursementMonth, formatCurrency, formatDate } from "../utils/format";
import type { Attachment, Expense, ExpenseCreatePayload, InvoicePoolItem, User } from "../types";

const props = defineProps<{
  user: User;
  refreshKey: number;
}>();

// ── State ────────────────────────────────────────────────
const expenses = ref<Expense[]>([]);
const invoicePool = ref<InvoicePoolItem[]>([]);
const uploadedAttachments = ref<Attachment[]>([]);
const loading = ref(false);
const error = ref("");
const success = ref("");

// Path 1 form
const expenseForm = ref({
  project_name: "",
  actual_amount: "",
  expense_month: currentReimbursementMonth(),
  category: DEFAULT_EXPENSE_CATEGORY,
});

// Selection
const selectedExpenseId = ref<number | null>(null);
const selectedInvoiceKeys = ref<string[]>([]);
const allocationNote = ref("");

// Actions
const saving = ref(false);
const matching = ref(false);
const pooling = ref(false);
const submittingId = ref<number | null>(null);
const deletingExpenseId = ref<number | null>(null);
const deletingAttachmentId = ref<number | null>(null);
const transactionInputRef = ref<HTMLInputElement | null>(null);
const transactionTargetExpenseId = ref<number | null>(null);
const transactionUploadingExpenseId = ref<number | null>(null);

// ── Computed ─────────────────────────────────────────────
const thisMonth = currentReimbursementMonth();

const pendingExpenses = computed(() => expenses.value.filter((e) => e.status === "pending"));
const submittedExpenses = computed(() => expenses.value.filter((e) => e.status === "matched"));
const monthlySubmittedTotal = computed(() =>
  expenses.value
    .filter((e) => e.expense_month === thisMonth && (e.status === "matched" || e.status === "reviewed"))
    .reduce((sum, e) => sum + Number(e.actual_amount), 0)
);

const selectedExpense = computed(() =>
  expenses.value.find((e) => e.id === selectedExpenseId.value) ?? null
);
const selectedInvoices = computed(() =>
  invoicePool.value.filter((item) => selectedInvoiceKeys.value.includes(invoiceKey(item)))
);
const selectedInvoiceTotal = computed(() =>
  selectedInvoices.value.reduce((sum, item) => sum + Number(item.invoice_amount), 0)
);
const stagedInvoiceTotal = computed(() =>
  roundCurrency(stagedInvoiceRefs(uploadedAttachments.value).reduce((sum, inv) => sum + inv.invoice_amount, 0))
);
const combinedInvoiceTotal = computed(() =>
  roundCurrency(stagedInvoiceTotal.value + selectedInvoiceTotal.value)
);
const workTarget = computed(() =>
  selectedExpense.value ? Number(selectedExpense.value.actual_amount) : 0
);
const workDiff = computed(() =>
  roundCurrency(combinedInvoiceTotal.value - workTarget.value)
);
const canSubmit = computed(() =>
  selectedExpense.value && selectedExpense.value.remaining_amount <= 0 && selectedExpense.value.allocated_amount > 0
);
const needsSubstituteNote = computed(() => workDiff.value > 0);
const workBarReady = computed(() => {
  if (matching.value || saving.value) return false;
  if (workTarget.value <= 0) return false;
  if (combinedInvoiceTotal.value < workTarget.value) return false;
  if (needsSubstituteNote.value && !allocationNote.value.trim()) return false;
  return true;
});

const usableInvoices = computed(() => invoicePool.value.filter((i) => i.remaining_amount > 0));

// ── Helpers ──────────────────────────────────────────────
function invoiceKey(item: InvoicePoolItem): string {
  return `${item.attachment_id}:${item.invoice_item_index}`;
}
function roundCurrency(value: number): number {
  return Math.round(value * 100) / 100;
}
function stagedInvoiceRefs(attachments: Attachment[]) {
  return attachments.flatMap((attachment) =>
    (Array.isArray(attachment.ocr_result.invoice_items) ? attachment.ocr_result.invoice_items as Array<Record<string, unknown>> : [])
      .map((item, index) => ({ item, index }))
      .filter(({ item }) => typeof item.amount === "number" && item.amount > 0)
      .map(({ item, index }) => ({
        attachment_id: attachment.id,
        invoice_item_index: index,
        invoice_amount: Number(item.amount),
        invoice_buyer: typeof item.buyer === "string" ? item.buyer : "",
      }))
  );
}
function buyerStatusLabel(buyer: string): string {
  if (!buyer) return "未识别";
  const st = buyerMatchStatus(buyer);
  if (st === "partial") return `${buyer}（需确认）`;
  if (st === "none") return `${buyer}（不可用）`;
  return isDifferentAllowedBuyer(buyer, props.user.company_entity) ? `${buyer}（可用）` : buyer;
}
function buyerTone(buyer: string): string {
  const st = buyerMatchStatus(buyer);
  if (st === "exact" && !isDifferentAllowedBuyer(buyer, props.user.company_entity)) return "ok";
  if (st === "exact" || st === "partial") return "warn";
  return "danger";
}
function needsBuyerConfirmation(invoices: Array<{ invoice_buyer: string }>): boolean {
  return invoices.some((inv) => {
    const st = buyerMatchStatus(inv.invoice_buyer);
    return st === "partial" || (st === "exact" && isDifferentAllowedBuyer(inv.invoice_buyer, props.user.company_entity));
  });
}
function isTransactionImageFile(file: File): boolean {
  return file.type.startsWith("image/") || /\.(png|jpe?g|webp|gif|bmp)$/i.test(file.name);
}

// ── Load ─────────────────────────────────────────────────
async function load() {
  loading.value = true;
  error.value = "";
  try {
    const [expRows, invRows] = await Promise.all([listExpenses(), listInvoicePool()]);
    expenses.value = expRows;
    invoicePool.value = invRows;
  } catch (err) {
    error.value = err instanceof Error ? err.message : "加载失败";
  } finally {
    loading.value = false;
  }
}

// ── Select expense → load into work area ─────────────────
function selectExpense(expense: Expense) {
  if (selectedExpenseId.value === expense.id) {
    selectedExpenseId.value = null;
    selectedInvoiceKeys.value = [];
    allocationNote.value = "";
  } else {
    selectedExpenseId.value = expense.id;
    selectedInvoiceKeys.value = [];
    allocationNote.value = "";
    // Select invoices already allocated to this expense
    const allocAttachmentIds = new Set(expense.allocations.map((a) => a.attachment_id));
    selectedInvoiceKeys.value = invoicePool.value
      .filter((inv) => allocAttachmentIds.has(inv.attachment_id))
      .map(invoiceKey);
  }
}

function deselectExpense() {
  selectedExpenseId.value = null;
  selectedInvoiceKeys.value = [];
  allocationNote.value = "";
}

// ── Path 1: Save expense only ────────────────────────────
function resetForm() {
  expenseForm.value = {
    project_name: "",
    actual_amount: "",
    expense_month: currentReimbursementMonth(),
    category: DEFAULT_EXPENSE_CATEGORY,
  };
}

async function saveExpense() {
  const data: ExpenseCreatePayload = {
    project_name: expenseForm.value.project_name.trim(),
    actual_amount: Number(expenseForm.value.actual_amount),
    expense_month: expenseForm.value.expense_month,
    category: expenseForm.value.category,
  };
  if (!data.project_name) { error.value = "请填写项目名称"; return; }
  if (!data.actual_amount || data.actual_amount <= 0) { error.value = "请填写金额"; return; }

  saving.value = true;
  error.value = "";
  success.value = "";
  try {
    const created = await createExpenseDraft(data);
    resetForm();
    await load();
    selectedExpenseId.value = created.id;
    success.value = `「${created.project_name}」已加入待处理`;
  } catch (err) {
    error.value = err instanceof Error ? err.message : "保存失败";
  } finally {
    saving.value = false;
  }
}

// ── Invoice upload → auto-pool ───────────────────────────
async function handleUploaded(attachments: Attachment[]) {
  if (!attachments.length) return;
  error.value = "";
  uploadedAttachments.value = [...attachments, ...uploadedAttachments.value];
  await addUploadedToPool();
}

async function addUploadedToPool() {
  if (!uploadedAttachments.value.length) return;
  const refs = stagedInvoiceRefs(uploadedAttachments.value);
  if (!refs.length) { error.value = "未识别到可入池的票据条目"; return; }

  pooling.value = true;
  try {
    await addAttachmentsToInvoicePool(uploadedAttachments.value.map((a) => a.id));
    await load();
    const newIds = new Set(uploadedAttachments.value.map((a) => a.id));
    const newKeys = invoicePool.value
      .filter((item) => newIds.has(item.attachment_id) && item.remaining_amount > 0)
      .map(invoiceKey);
    selectedInvoiceKeys.value = [...selectedInvoiceKeys.value, ...newKeys];
    uploadedAttachments.value = [];
    success.value = "发票已识别并入池，已自动选中";
  } catch (err) {
    error.value = err instanceof Error ? err.message : "入池失败";
  } finally {
    pooling.value = false;
  }
}

async function removeUploaded(id: number) {
  if (!window.confirm("删除这份发票文件吗？")) return;
  deletingAttachmentId.value = id;
  try {
    await deleteAttachment(id);
    const removed = uploadedAttachments.value.find((a) => a.id === id);
    if (removed?.preview_url) URL.revokeObjectURL(removed.preview_url);
    uploadedAttachments.value = uploadedAttachments.value.filter((a) => a.id !== id);
    selectedInvoiceKeys.value = selectedInvoiceKeys.value.filter((k) => !k.startsWith(`${id}:`));
    await load();
    success.value = "发票已删除";
  } catch (err) {
    error.value = err instanceof Error ? err.message : "删除失败";
  } finally {
    deletingAttachmentId.value = null;
  }
}

// ── Path 2: Combined create+match ────────────────────────
async function saveAndSubmit() {
  const invoiceRefs = stagedInvoiceRefs(uploadedAttachments.value);
  if (!invoiceRefs.length) { error.value = "请先上传发票"; return; }

  const actualAmount = Number(expenseForm.value.actual_amount) || stagedInvoiceTotal.value;
  const projectName = expenseForm.value.project_name.trim() || "未命名花费";
  const buyerConfirmed = needsBuyerConfirmation(invoiceRefs);
  if (buyerConfirmed && !window.confirm("有发票抬头不一致，请确认后继续。")) return;

  saving.value = true;
  error.value = "";
  success.value = "";
  try {
    if (stagedInvoiceTotal.value >= actualAmount) {
      await createAndSubmitExpense({
        project_name: projectName,
        actual_amount: actualAmount,
        expense_month: expenseForm.value.expense_month,
        category: expenseForm.value.category,
        invoices: invoiceRefs.map((inv) => ({
          attachment_id: inv.attachment_id,
          invoice_item_index: inv.invoice_item_index,
        })),
        attachment_ids: [],
        note: stagedInvoiceTotal.value > actualAmount ? allocationNote.value.trim() : "",
        buyer_confirmed: buyerConfirmed,
      });
      success.value = stagedInvoiceTotal.value > actualAmount ? "已记录并提交（替票）" : "已记录并提交";
      resetForm();
      uploadedAttachments.value = [];
      await load();
    } else {
      await addUploadedToPool();
      const created = await createExpenseDraft({
        project_name: projectName,
        actual_amount: actualAmount,
        expense_month: expenseForm.value.expense_month,
        category: expenseForm.value.category,
      });
      await createExpenseAllocationsBatch({
        expense_id: created.id,
        invoices: invoiceRefs.map((inv) => ({
          attachment_id: inv.attachment_id,
          invoice_item_index: inv.invoice_item_index,
        })),
        note: "",
        buyer_confirmed: buyerConfirmed,
      });
      resetForm();
      await load();
      success.value = "发票金额不足，已加入待处理，请继续补充发票";
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : "操作失败";
  } finally {
    saving.value = false;
  }
}

// ── Toggle invoice in pool ───────────────────────────────
function toggleInvoice(invoice: InvoicePoolItem) {
  const key = invoiceKey(invoice);
  selectedInvoiceKeys.value = selectedInvoiceKeys.value.includes(key)
    ? selectedInvoiceKeys.value.filter((k) => k !== key)
    : [...selectedInvoiceKeys.value, key];
}

// ── Match selected invoices to selected expense ──────────
async function performMatch() {
  if (!selectedExpense.value || !selectedInvoices.value.length) return;
  const invoiceRefs = selectedInvoices.value.map((inv) => ({
    attachment_id: inv.attachment_id,
    invoice_item_index: inv.invoice_item_index,
  }));
  const buyerConfirmed = needsBuyerConfirmation(selectedInvoices.value);
  if (buyerConfirmed && !window.confirm("有发票抬头不一致，请确认后继续。")) return;
  if (needsSubstituteNote.value && !allocationNote.value.trim()) {
    error.value = "票面超出花费金额，请填写替票说明";
    return;
  }

  matching.value = true;
  error.value = "";
  success.value = "";
  try {
    await createExpenseAllocationsBatch({
      expense_id: selectedExpense.value.id,
      invoices: invoiceRefs,
      note: needsSubstituteNote.value ? allocationNote.value.trim() : "",
      buyer_confirmed: buyerConfirmed,
    });
    selectedInvoiceKeys.value = [];
    allocationNote.value = "";
    await load();
    // Check if now ready to submit
    const updated = expenses.value.find((e) => e.id === selectedExpenseId.value);
    if (updated && updated.remaining_amount <= 0) {
      success.value = "匹配完成！金额已满足，点击下方「确认提交」即可";
    } else {
      success.value = "发票已匹配到花费";
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : "匹配失败";
  } finally {
    matching.value = false;
  }
}

// ── Submit / Withdraw / Delete ───────────────────────────
async function handleSubmit() {
  if (!selectedExpense.value) return;
  if (!window.confirm(`确认提交「${selectedExpense.value.project_name}」？提交后将锁定。`)) return;
  submittingId.value = selectedExpense.value.id;
  error.value = "";
  success.value = "";
  try {
    await submitExpense(selectedExpense.value.id);
    await load();
    selectedExpenseId.value = null;
    selectedInvoiceKeys.value = [];
    success.value = "已提交";
  } catch (err) {
    error.value = err instanceof Error ? err.message : "提交失败";
  } finally {
    submittingId.value = null;
  }
}

async function handleWithdraw(expense: Expense) {
  if (!window.confirm(`撤回「${expense.project_name}」？回到待处理区。`)) return;
  try {
    await withdrawExpense(expense.id);
    await load();
    success.value = "已撤回";
  } catch (err) {
    error.value = err instanceof Error ? err.message : "撤回失败";
  }
}

async function handleDeleteExpense(expense: Expense) {
  if (!window.confirm(`删除「${expense.project_name}」？不可恢复。`)) return;
  deletingExpenseId.value = expense.id;
  try {
    await deleteExpense(expense.id);
    if (selectedExpenseId.value === expense.id) {
      selectedExpenseId.value = null;
      selectedInvoiceKeys.value = [];
    }
    await load();
    success.value = "已删除";
  } catch (err) {
    error.value = err instanceof Error ? err.message : "删除失败";
  } finally {
    deletingExpenseId.value = null;
  }
}

// ── Transaction attachments ──────────────────────────────
function triggerTransactionUpload(expense: Expense) {
  transactionTargetExpenseId.value = expense.id;
  transactionInputRef.value?.click();
}

async function handleTransactionFiles(event: Event) {
  const input = event.target as HTMLInputElement;
  const expenseId = transactionTargetExpenseId.value;
  const files = Array.from(input.files ?? []).filter(isTransactionImageFile);
  input.value = "";
  if (!expenseId || !files.length) return;

  transactionUploadingExpenseId.value = expenseId;
  error.value = "";
  try {
    const attachments = await uploadAttachments(files);
    await linkExpenseAttachments(expenseId, { attachment_ids: attachments.map((a) => a.id) });
    await load();
    success.value = "佐证材料已上传";
  } catch (err) {
    error.value = err instanceof Error ? err.message : "上传失败";
  } finally {
    transactionUploadingExpenseId.value = null;
    transactionTargetExpenseId.value = null;
  }
}

async function deleteTransactionAttachment(expense: Expense, attachment: Attachment) {
  if (!window.confirm(`删除「${attachment.original_filename}」？`)) return;
  try {
    await deleteExpenseAttachment(expense.id, attachment.id);
    await load();
    success.value = "附件已删除";
  } catch (err) {
    error.value = err instanceof Error ? err.message : "删除失败";
  }
}

async function deleteInvoiceFromPool(invoice: InvoicePoolItem) {
  if (!window.confirm(`删除发票「${invoice.attachment_name}」？`)) return;
  deletingAttachmentId.value = invoice.attachment_id;
  try {
    await deleteAttachment(invoice.attachment_id);
    selectedInvoiceKeys.value = selectedInvoiceKeys.value.filter((k) => !k.startsWith(`${invoice.attachment_id}:`));
    await load();
    success.value = "发票已删除";
  } catch (err) {
    error.value = err instanceof Error ? err.message : "删除失败";
  } finally {
    deletingAttachmentId.value = null;
  }
}

onMounted(load);
</script>

<template>
  <div class="mx-auto max-w-7xl space-y-5">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="page-title">当月报销</h1>
        <p class="muted mt-1">{{ user.employee_name }}，{{ thisMonth }}</p>
      </div>
      <div class="text-right text-sm text-slate-500">
        <span class="text-xs text-slate-400">本月已提交</span>
        <div class="text-lg font-semibold text-teal-700">{{ formatCurrency(monthlySubmittedTotal) }}</div>
      </div>
    </div>

    <p v-if="error" class="rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-700">{{ error }}</p>
    <p v-if="success" class="rounded-md bg-teal-50 px-3 py-2 text-sm text-teal-800">{{ success }}</p>

    <!-- ═══ Work Panel ═══ -->
    <section class="tool-panel overflow-hidden rounded-lg">
      <div class="border-b border-slate-200 px-5 py-4">
        <h2 class="section-title">{{ selectedExpense ? selectedExpense.project_name || selectedExpense.category : "记一笔" }}</h2>
      </div>

      <!-- State A: New expense (no selection) -->
      <div v-if="!selectedExpense" class="p-5">
        <div class="grid gap-5 lg:grid-cols-2">
          <!-- Path 1 -->
          <div class="space-y-3">
            <div class="text-xs font-semibold uppercase tracking-normal text-slate-400">路径一：先记账，后补票</div>
            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="field-label" for="exp-project">项目名称</label>
                <input id="exp-project" v-model="expenseForm.project_name" class="field-input mt-1" placeholder="如：客户拜访打车" />
              </div>
              <div>
                <label class="field-label" for="exp-amount">金额</label>
                <input id="exp-amount" v-model="expenseForm.actual_amount" class="field-input mt-1" inputmode="decimal" />
              </div>
            </div>
            <div>
              <label class="field-label" for="exp-cat">类别</label>
              <select id="exp-cat" v-model="expenseForm.category" class="field-input mt-1">
                <option v-for="cat in EXPENSE_CATEGORIES" :key="cat">{{ cat }}</option>
              </select>
            </div>
            <button
              class="primary-button w-full justify-center"
              type="button"
              :disabled="saving || !expenseForm.project_name.trim() || Number(expenseForm.actual_amount) <= 0"
              @click="saveExpense"
            >
              <PlusCircle class="h-4 w-4" />
              {{ saving ? "保存中..." : "保存到待处理" }}
            </button>
          </div>

          <!-- Path 2 -->
          <div class="space-y-3 border-t border-slate-100 pt-5 lg:border-l lg:border-t-0 lg:pl-5 lg:pt-0">
            <div class="text-xs font-semibold uppercase tracking-normal text-slate-400">路径二：发票和账一起记</div>
            <InvoiceUploadPanel
              :attachments="uploadedAttachments"
              :current-company="user.company_entity"
              :removing-id="deletingAttachmentId"
              :pooling="pooling"
              @uploaded="handleUploaded"
              @add-to-pool="addUploadedToPool"
              @remove="removeUploaded"
            />
            <div v-if="uploadedAttachments.length" class="grid grid-cols-2 gap-3">
              <input v-model="expenseForm.project_name" class="field-input" placeholder="项目名称（可选）" />
              <input v-model="expenseForm.actual_amount" class="field-input" inputmode="decimal" :placeholder="stagedInvoiceTotal ? String(stagedInvoiceTotal) : '金额'" />
            </div>
            <button
              v-if="uploadedAttachments.length"
              class="primary-button w-full justify-center"
              type="button"
              :disabled="saving"
              @click="saveAndSubmit"
            >
              <Link2 class="h-4 w-4" />
              {{ saving ? "处理中..." : stagedInvoiceTotal >= Number(expenseForm.actual_amount || stagedInvoiceTotal) ? "记录并提交" : "记录到待处理" }}
            </button>
          </div>
        </div>
      </div>

      <!-- State B: Selected expense — work on it -->
      <div v-else class="p-5">
        <div class="mb-4 flex items-center justify-between">
          <div>
            <div class="flex items-center gap-3">
              <span class="status-pill bg-amber-50 text-amber-700">待处理</span>
              <span class="text-xs text-slate-500">{{ selectedExpense.expense_month }} · {{ selectedExpense.category }}</span>
            </div>
            <div v-if="selectedExpense.reject_reason" class="mt-2 rounded bg-rose-50 px-2 py-1 text-xs text-rose-700">
              打回原因：{{ selectedExpense.reject_reason }}
            </div>
          </div>
          <button class="text-xs text-slate-500 transition hover:text-rose-600" type="button" @click="deselectExpense">
            取消选择
          </button>
        </div>

        <!-- Amount summary -->
        <div class="mb-5 grid grid-cols-3 gap-3">
          <div class="rounded-lg border border-slate-200 bg-white p-3 text-center">
            <div class="text-xs text-slate-500">花费金额</div>
            <div class="mt-1 text-lg font-bold text-ink">{{ formatCurrency(selectedExpense.actual_amount) }}</div>
          </div>
          <div class="rounded-lg border border-slate-200 bg-white p-3 text-center">
            <div class="text-xs text-slate-500">已匹配发票</div>
            <div class="mt-1 text-lg font-bold text-teal-700">{{ formatCurrency(selectedExpense.allocated_amount) }}</div>
          </div>
          <div class="rounded-lg border p-3 text-center" :class="selectedExpense.remaining_amount <= 0 ? 'border-teal-200 bg-teal-50' : 'border-amber-200 bg-amber-50'">
            <div class="text-xs" :class="selectedExpense.remaining_amount <= 0 ? 'text-teal-600' : 'text-amber-600'">
              {{ selectedExpense.remaining_amount <= 0 ? '已满足' : '还差' }}
            </div>
            <div class="mt-1 text-lg font-bold" :class="selectedExpense.remaining_amount <= 0 ? 'text-teal-700' : 'text-amber-700'">
              {{ selectedExpense.remaining_amount <= 0 ? '✓' : formatCurrency(selectedExpense.remaining_amount) }}
            </div>
          </div>
        </div>

        <!-- Transaction attachments -->
        <div v-if="selectedExpense.attachments.length" class="mb-4 flex flex-wrap items-center gap-2">
          <span class="text-xs text-slate-500">佐证材料：</span>
          <div v-for="att in selectedExpense.attachments" :key="att.id"
            class="inline-flex items-center gap-1 rounded-md bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
            <AttachmentThumb :attachment="att" />
            <span class="max-w-24 truncate">{{ att.original_filename }}</span>
            <button class="text-slate-400 hover:text-rose-600" @click="deleteTransactionAttachment(selectedExpense, att)"><X class="h-3 w-3" /></button>
          </div>
        </div>

        <!-- Allocated invoices display -->
        <div v-if="selectedExpense.allocations.length" class="mb-4">
          <div class="mb-2 text-xs text-slate-500">已匹配发票：</div>
          <div class="flex flex-wrap gap-2">
            <div v-for="alloc in selectedExpense.allocations" :key="alloc.id"
              class="rounded-md border border-teal-200 bg-teal-50 px-3 py-1.5 text-xs text-teal-800">
              {{ alloc.invoice_type }} · {{ formatCurrency(alloc.allocated_amount) }}
            </div>
          </div>
        </div>

        <!-- Invoice upload + Selected invoices from pool -->
        <div class="grid gap-5 lg:grid-cols-2">
          <!-- Upload new invoices -->
          <div>
            <div class="mb-2 text-xs font-semibold text-slate-500">上传新发票</div>
            <InvoiceUploadPanel
              :attachments="uploadedAttachments"
              :current-company="user.company_entity"
              :removing-id="deletingAttachmentId"
              :pooling="pooling"
              @uploaded="handleUploaded"
              @add-to-pool="addUploadedToPool"
              @remove="removeUploaded"
            />
          </div>

          <!-- Selected from pool -->
          <div>
            <div class="mb-2 text-xs font-semibold text-slate-500">
              从发票池已选 {{ selectedInvoices.length }} 张
              <span v-if="selectedInvoiceTotal" class="ml-2 text-teal-700">{{ formatCurrency(selectedInvoiceTotal) }}</span>
            </div>
            <div v-if="!selectedInvoices.length" class="text-xs text-slate-400">
              在下方发票池勾选发票，或上传新发票自动选中
            </div>
            <div v-else class="space-y-2">
              <div v-for="invoice in selectedInvoices" :key="invoiceKey(invoice)"
                class="flex items-center justify-between rounded-md border border-slate-200 bg-white px-3 py-2">
                <div class="min-w-0">
                  <div class="truncate text-sm font-medium text-ink">{{ invoice.invoice_type }}</div>
                  <div class="truncate text-xs text-slate-500">{{ invoice.attachment_name }}</div>
                </div>
                <div class="flex shrink-0 items-center gap-2">
                  <span class="text-sm font-semibold text-ink">{{ formatCurrency(invoice.invoice_amount) }}</span>
                  <button class="text-slate-400 hover:text-rose-600" @click="toggleInvoice(invoice)"><X class="h-4 w-4" /></button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Action bar -->
        <div v-if="canSubmit" class="mt-5 rounded-lg border-2 border-teal-300 bg-teal-50 p-5">
          <div class="flex flex-wrap items-center justify-between gap-4">
            <div>
              <div class="flex items-center gap-2 text-teal-800">
                <CheckCircle2 class="h-5 w-5" />
                <span class="font-semibold">金额已满足，可以提交</span>
              </div>
              <div class="mt-1 text-sm text-teal-700">
                发票合计 {{ formatCurrency(selectedExpense!.allocated_amount) }}，花费 {{ formatCurrency(selectedExpense!.actual_amount) }}
              </div>
            </div>
            <div class="flex items-center gap-2">
              <button class="text-xs text-teal-700 hover:text-teal-900 flex items-center gap-1"
                @click="triggerTransactionUpload(selectedExpense!)">
                <ImagePlus class="h-3.5 w-3.5" /> 补材料
              </button>
              <button
                class="primary-button h-10 px-6 text-base"
                :disabled="submittingId === selectedExpense!.id"
                @click="handleSubmit"
              >
                <template v-if="submittingId === selectedExpense!.id">
                  <Loader2 class="h-4 w-4 animate-spin" />
                </template>
                <template v-else>
                  确认提交 <ArrowRight class="h-4 w-4" />
                </template>
              </button>
            </div>
          </div>
        </div>

        <div v-else class="mt-5 flex flex-wrap items-center justify-between gap-4 border-t border-slate-200 pt-5">
          <div class="flex items-center gap-3">
            <div v-if="combinedInvoiceTotal > 0" class="flex items-center gap-2 text-sm">
              <span class="text-slate-500">发票合计</span>
              <span class="font-bold text-teal-700">{{ formatCurrency(combinedInvoiceTotal) }}</span>
              <span v-if="workDiff > 0" class="text-xs text-amber-700">超出 {{ formatCurrency(workDiff) }}</span>
              <span v-else-if="workDiff < 0" class="text-xs text-amber-700">还差 {{ formatCurrency(Math.abs(workDiff)) }}</span>
              <span v-else class="text-xs text-teal-700">刚好匹配</span>
            </div>
            <span v-else class="text-xs text-slate-400">请上传发票或从下方发票池选择</span>
          </div>
          <div class="flex items-center gap-2">
            <button class="text-xs text-slate-500 hover:text-teal-700 flex items-center gap-1"
              @click="triggerTransactionUpload(selectedExpense!)">
              <ImagePlus class="h-3.5 w-3.5" /> 补材料
            </button>
            <button
              class="primary-button h-9 px-4"
              type="button"
              :disabled="!workBarReady || matching"
              @click="performMatch"
            >
              <Loader2 v-if="matching" class="h-4 w-4 animate-spin" />
              <Link2 v-else class="h-4 w-4" />
              {{ matching ? "匹配中..." : "匹配发票" }}
            </button>
          </div>
        </div>

        <div v-if="needsSubstituteNote" class="mt-3">
          <textarea v-model="allocationNote" class="field-textarea min-h-14" rows="2" placeholder="票面超出花费金额，请填写替票说明" />
        </div>
      </div>
    </section>

    <input ref="transactionInputRef" class="hidden" type="file" accept="image/*" multiple @change="handleTransactionFiles" />

    <!-- ═══ 待处理 / 已提交 Tabs ═══ -->
    <section class="tool-panel overflow-hidden rounded-lg">
      <div class="border-b border-slate-200 px-5 py-4">
        <div class="flex items-center justify-between">
          <h2 class="section-title">待处理</h2>
          <span class="text-xs text-slate-500">点击花费卡片或发票卡片进行匹配</span>
        </div>
      </div>

      <div v-if="!pendingExpenses.length && !usableInvoices.length" class="empty-state">
        <div class="empty-state-icon"><ReceiptText class="h-6 w-6" /></div>
        <div>
          <div class="text-sm font-medium text-slate-700">暂无待处理项</div>
          <div class="mt-1 text-xs text-slate-500">在上方录入花费或上传发票。</div>
        </div>
      </div>

      <div v-else class="grid gap-5 p-5 lg:grid-cols-2">
        <!-- Expense cards -->
        <div>
          <div class="mb-3 text-xs font-semibold uppercase tracking-normal text-slate-400">
            花费（{{ pendingExpenses.length }}）
          </div>
          <div v-if="!pendingExpenses.length" class="text-xs text-slate-400">暂无</div>
          <div class="space-y-3">
            <article
              v-for="expense in pendingExpenses"
              :key="expense.id"
              class="cursor-pointer rounded-lg border p-4 transition"
              :class="selectedExpenseId === expense.id ? 'border-teal-400 bg-teal-50/60 ring-2 ring-teal-700/10' : 'border-slate-200 bg-white hover:border-teal-300'"
              @click="selectExpense(expense)"
            >
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <div class="truncate text-sm font-semibold text-ink">{{ expense.project_name || expense.category }}</div>
                  <div class="mt-1 text-xs text-slate-500">{{ expense.expense_month }} · {{ expense.category }}</div>
                </div>
                <button
                  class="grid h-8 w-8 shrink-0 place-items-center rounded-md text-slate-400 transition hover:bg-rose-50 hover:text-rose-700"
                  :disabled="deletingExpenseId === expense.id"
                  @click.stop="handleDeleteExpense(expense)"
                >
                  <Loader2 v-if="deletingExpenseId === expense.id" class="h-4 w-4 animate-spin" />
                  <Trash2 v-else class="h-4 w-4" />
                </button>
              </div>
              <div class="mt-3 grid grid-cols-3 gap-2 text-xs">
                <div class="match-mini-stat"><span>花费</span><strong>{{ formatCurrency(expense.actual_amount) }}</strong></div>
                <div class="match-mini-stat"><span>已匹配</span><strong>{{ formatCurrency(expense.allocated_amount) }}</strong></div>
                <div class="match-mini-stat"><span>待匹配</span><strong>{{ formatCurrency(expense.remaining_amount) }}</strong></div>
              </div>
            </article>
          </div>
        </div>

        <!-- Invoice pool -->
        <div>
          <div class="mb-3 text-xs font-semibold uppercase tracking-normal text-slate-400">
            发票池（{{ usableInvoices.length }}）
          </div>
          <div v-if="!usableInvoices.length" class="text-xs text-slate-400">暂无可用发票</div>
          <div class="space-y-2">
            <article
              v-for="invoice in usableInvoices"
              :key="invoiceKey(invoice)"
              class="cursor-pointer rounded-lg border p-3 transition"
              :class="selectedInvoiceKeys.includes(invoiceKey(invoice)) ? 'border-teal-400 bg-teal-50/60 ring-2 ring-teal-700/10' : 'border-slate-200 bg-white hover:border-teal-300'"
              @click="toggleInvoice(invoice)"
            >
              <div class="flex items-start justify-between gap-2">
                <div class="min-w-0 flex-1">
                  <div class="truncate text-sm font-medium text-ink">{{ invoice.invoice_type }}</div>
                  <div class="mt-0.5 truncate text-xs text-slate-500">{{ invoice.attachment_name }}</div>
                </div>
                <span class="shrink-0 text-sm font-semibold text-ink">{{ formatCurrency(invoice.invoice_amount) }}</span>
              </div>
              <div class="mt-2 flex items-center justify-between text-xs">
                <span :class="{
                  'text-teal-700': buyerTone(invoice.invoice_buyer) === 'ok',
                  'text-amber-700': buyerTone(invoice.invoice_buyer) === 'warn',
                  'text-rose-700': buyerTone(invoice.invoice_buyer) === 'danger',
                }">
                  {{ buyerStatusLabel(invoice.invoice_buyer) }}
                </span>
                <div class="flex items-center gap-2">
                  <span class="text-slate-400">{{ invoice.invoice_date || formatDate(invoice.created_at) }}</span>
                  <button class="text-slate-300 hover:text-rose-600"
                    :disabled="deletingAttachmentId === invoice.attachment_id"
                    @click.stop="deleteInvoiceFromPool(invoice)">
                    <X class="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            </article>
          </div>
        </div>
      </div>
    </section>

    <!-- ═══ 已提交 Table ═══ -->
    <section class="tool-panel overflow-hidden rounded-lg">
      <div class="flex items-center justify-between border-b border-slate-200 px-5 py-4">
        <div>
          <h2 class="section-title">已提交</h2>
          <p class="muted mt-1">本月已提交、等待管理员审核</p>
        </div>
      </div>

      <div v-if="loading" class="px-5 py-12 text-center text-sm text-slate-500">加载中...</div>
      <div v-else-if="!submittedExpenses.length" class="empty-state">
        <div class="empty-state-icon"><CheckCircle2 class="h-6 w-6" /></div>
        <div>
          <div class="text-sm font-medium text-slate-700">暂无已提交记录</div>
          <div class="mt-1 text-xs text-slate-500">在待处理区完成匹配后点击提交即可。</div>
        </div>
      </div>

      <div v-else class="overflow-x-auto">
        <table class="min-w-full divide-y divide-slate-200 text-left text-sm">
          <thead class="bg-slate-50 text-xs font-medium uppercase tracking-normal text-slate-500">
            <tr>
              <th class="px-5 py-3">项目</th>
              <th class="px-5 py-3">类别</th>
              <th class="px-5 py-3">金额</th>
              <th class="px-5 py-3">发票</th>
              <th class="px-5 py-3">佐证</th>
              <th class="px-5 py-3">替票</th>
              <th class="px-5 py-3">操作</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100 bg-white">
            <tr v-for="expense in submittedExpenses" :key="expense.id" class="hover:bg-slate-50/70">
              <td class="px-5 py-4 font-medium text-slate-900">{{ expense.project_name || expense.category }}</td>
              <td class="px-5 py-4 text-slate-600">{{ expense.category }}</td>
              <td class="px-5 py-4 font-medium text-slate-900">{{ formatCurrency(expense.actual_amount) }}</td>
              <td class="px-5 py-4 text-slate-600">{{ expense.allocation_count }} 张</td>
              <td class="px-5 py-4 text-slate-600">{{ expense.attachments.length }} 个</td>
              <td class="px-5 py-4">
                <span class="status-pill" :class="expense.is_substitute ? 'bg-amber-50 text-amber-700' : 'bg-slate-100 text-slate-600'">
                  {{ expense.is_substitute ? "是" : "否" }}
                </span>
              </td>
              <td class="px-5 py-4">
                <div class="flex items-center gap-2">
                  <button class="text-xs text-slate-500 hover:text-teal-700 flex items-center gap-1"
                    @click="triggerTransactionUpload(expense)">
                    <ImagePlus class="h-3.5 w-3.5" /> 补材料
                  </button>
                  <button class="secondary-button h-8 px-2 text-xs" @click="handleWithdraw(expense)">撤回</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>
