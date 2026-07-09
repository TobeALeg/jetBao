<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import {
  CheckCircle2, ImagePlus,
  Link2, Loader2, PlusCircle, ReceiptText, X
} from "lucide-vue-next";
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

const emit = defineEmits<{
  refreshed: [];
  "open-materials": [];
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
const formedExpenses = computed(() => expenses.value.filter((e) => e.status === "matched" || e.status === "reviewed"));
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
const normalInvoiceRefs = computed(() => [
  ...stagedInvoiceRefs(uploadedAttachments.value),
  ...selectedInvoices.value.map((inv) => ({
    attachment_id: inv.attachment_id,
    invoice_item_index: inv.invoice_item_index,
    invoice_amount: Number(inv.invoice_amount),
    invoice_buyer: inv.invoice_buyer,
  })),
]);
const normalInvoiceTotal = computed(() =>
  roundCurrency(normalInvoiceRefs.value.reduce((sum, inv) => sum + inv.invoice_amount, 0))
);
const normalActualAmount = computed(() => Number(expenseForm.value.actual_amount) || 0);
const normalOutcome = computed(() => {
  if (!normalInvoiceRefs.value.length || normalActualAmount.value <= 0) return "";
  return normalInvoiceTotal.value === normalActualAmount.value ? "真实票" : "替票";
});
const canCreateAndSubmit = computed(() =>
  Boolean(expenseForm.value.project_name.trim()) &&
  normalActualAmount.value > 0 &&
  normalInvoiceRefs.value.length > 0
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
  if (combinedInvoiceTotal.value <= 0) return false;
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
    emit("refreshed");
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

function beginNewExpense() {
  deselectExpense();
  selectedInvoiceKeys.value = [];
  uploadedAttachments.value = [];
  allocationNote.value = "";
  resetForm();
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
    selectedExpenseId.value = null;
    success.value = `「${created.project_name}」已保存到待补材料`;
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

async function handleNormalUploaded(attachments: Attachment[]) {
  if (!attachments.length) return;
  error.value = "";
  uploadedAttachments.value = [...attachments, ...uploadedAttachments.value];
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
  const invoiceRefs = normalInvoiceRefs.value;
  if (!invoiceRefs.length) { error.value = "请先上传发票"; return; }

  const actualAmount = Number(expenseForm.value.actual_amount);
  const projectName = expenseForm.value.project_name.trim();
  if (!projectName) { error.value = "请填写报销事项"; return; }
  if (!actualAmount || actualAmount <= 0) { error.value = "请填写金额"; return; }
  const buyerConfirmed = needsBuyerConfirmation(invoiceRefs);
  if (buyerConfirmed && !window.confirm("有发票抬头不一致，请确认后继续。")) return;

  saving.value = true;
  error.value = "";
  success.value = "";
  try {
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
      note: "",
      buyer_confirmed: buyerConfirmed,
    });
    success.value = normalOutcome.value === "替票" ? "已提交（替票）" : "已提交";
    resetForm();
    uploadedAttachments.value = [];
    selectedInvoiceKeys.value = [];
    await load();
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
  matching.value = true;
  error.value = "";
  success.value = "";
  try {
    await createExpenseAllocationsBatch({
      expense_id: selectedExpense.value.id,
      invoices: invoiceRefs,
      note: "",
      buyer_confirmed: buyerConfirmed,
    });
    selectedInvoiceKeys.value = [];
    allocationNote.value = "";
    await load();
    // Check if now ready to submit
    const updated = expenses.value.find((e) => e.id === selectedExpenseId.value);
    if (updated && updated.allocated_amount > 0) {
      success.value = updated.is_substitute ? "已归属发票（替票）" : "已归属发票";
    } else {
      success.value = "发票已归属到报销";
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
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 class="page-title">我的报销</h1>
        <p class="muted mt-1">{{ user.employee_name }}，{{ thisMonth }}</p>
      </div>
      <div class="flex items-center gap-2">
        <button class="secondary-button" type="button" @click="$emit('open-materials')">
          待补材料
          <span v-if="pendingExpenses.length || usableInvoices.length" class="nav-badge">
            {{ pendingExpenses.length + usableInvoices.length }}
          </span>
        </button>
        <button class="primary-button" type="button" @click="beginNewExpense">
          <PlusCircle class="h-4 w-4" />
          新建报销
        </button>
      </div>
    </div>

    <p v-if="error" class="rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-700">{{ error }}</p>
    <p v-if="success" class="rounded-md bg-teal-50 px-3 py-2 text-sm text-teal-800">{{ success }}</p>

    <section class="tool-panel overflow-hidden rounded-lg">
      <div class="flex items-center justify-between border-b border-slate-200 px-5 py-4">
        <div>
          <h2 class="section-title">新建报销</h2>
          <p class="muted mt-1">左侧填写报销，右侧添加发票。</p>
        </div>
        <div class="text-right">
          <div class="text-xs text-slate-400">本月已提交</div>
          <div class="text-lg font-semibold text-teal-700">{{ formatCurrency(monthlySubmittedTotal) }}</div>
        </div>
      </div>

      <div class="grid gap-0 lg:grid-cols-[minmax(0,0.92fr)_minmax(420px,1.08fr)]">
        <div class="space-y-4 border-b border-slate-200 p-5 lg:border-b-0 lg:border-r">
          <div class="grid gap-3 sm:grid-cols-2">
            <div class="sm:col-span-2">
              <label class="field-label" for="exp-project">报销事项</label>
              <input id="exp-project" v-model="expenseForm.project_name" class="field-input mt-1" placeholder="如：客户拜访打车" />
            </div>
            <div>
              <label class="field-label" for="exp-amount">金额</label>
              <input id="exp-amount" v-model="expenseForm.actual_amount" class="field-input mt-1" inputmode="decimal" />
            </div>
            <div>
              <label class="field-label" for="exp-month">月份</label>
              <input id="exp-month" v-model="expenseForm.expense_month" class="field-input mt-1" type="month" />
            </div>
            <div class="sm:col-span-2">
              <label class="field-label" for="exp-cat">类别</label>
              <select id="exp-cat" v-model="expenseForm.category" class="field-input mt-1">
                <option v-for="cat in EXPENSE_CATEGORIES" :key="cat">{{ cat }}</option>
              </select>
            </div>
          </div>

          <div class="grid gap-3 border-t border-slate-100 pt-4 sm:grid-cols-3">
            <div class="match-mini-stat">
              <span>发票</span>
              <strong>{{ normalInvoiceRefs.length }} 张</strong>
            </div>
            <div class="match-mini-stat">
              <span>报销金额</span>
              <strong>{{ normalActualAmount ? formatCurrency(normalActualAmount) : "未填" }}</strong>
            </div>
            <div class="match-mini-stat">
              <span>结果</span>
              <strong>{{ normalOutcome || "待添加" }}</strong>
            </div>
          </div>

          <div class="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-4">
            <button
              class="secondary-button"
              type="button"
              :disabled="saving || !expenseForm.project_name.trim() || Number(expenseForm.actual_amount) <= 0"
              @click="saveExpense"
            >
              保存到待补材料
            </button>
            <button
              class="primary-button"
              type="button"
              :disabled="saving || !canCreateAndSubmit"
              @click="saveAndSubmit"
            >
              <Loader2 v-if="saving" class="h-4 w-4 animate-spin" />
              <Link2 v-else class="h-4 w-4" />
              提交报销
            </button>
          </div>
        </div>

        <div class="space-y-4 p-5">
          <InvoiceUploadPanel
            :attachments="uploadedAttachments"
            :current-company="user.company_entity"
            :removing-id="deletingAttachmentId"
            :pooling="pooling"
            @uploaded="handleNormalUploaded"
            @add-to-pool="addUploadedToPool"
            @remove="removeUploaded"
          />

          <div class="border-t border-slate-100 pt-4">
            <div class="mb-3 flex items-center justify-between gap-3">
              <h3 class="text-xs font-semibold uppercase tracking-normal text-slate-400">选择已有发票</h3>
              <span class="text-xs text-slate-500">{{ selectedInvoices.length }} 张已选</span>
            </div>
            <div v-if="!usableInvoices.length" class="match-empty-copy min-h-28">
              <ReceiptText class="h-5 w-5 text-slate-400" />
              <span>暂无可用发票</span>
            </div>
            <div v-else class="grid gap-2 xl:grid-cols-2">
              <article
                v-for="invoice in usableInvoices"
                :key="invoiceKey(invoice)"
                class="cursor-pointer rounded-md border px-3 py-2 transition"
                :class="selectedInvoiceKeys.includes(invoiceKey(invoice)) ? 'border-teal-400 bg-teal-50/60 ring-2 ring-teal-700/10' : 'border-slate-200 bg-white hover:border-teal-300'"
                @click="toggleInvoice(invoice)"
              >
                <div class="flex items-start justify-between gap-2">
                  <div class="min-w-0">
                    <div class="truncate text-sm font-medium text-ink">{{ invoice.invoice_type }}</div>
                    <div class="mt-0.5 truncate text-xs text-slate-500">{{ invoice.attachment_name }}</div>
                  </div>
                  <span class="shrink-0 text-sm font-semibold text-ink">{{ formatCurrency(invoice.invoice_amount) }}</span>
                </div>
                <div class="mt-2 flex items-center justify-between gap-2 text-xs">
                  <span
                    class="truncate"
                    :class="{
                      'text-teal-700': buyerTone(invoice.invoice_buyer) === 'ok',
                      'text-amber-700': buyerTone(invoice.invoice_buyer) === 'warn',
                      'text-rose-700': buyerTone(invoice.invoice_buyer) === 'danger',
                    }"
                  >
                    {{ buyerStatusLabel(invoice.invoice_buyer) }}
                  </span>
                  <button
                    class="text-slate-300 hover:text-rose-600"
                    type="button"
                    :disabled="deletingAttachmentId === invoice.attachment_id"
                    @click.stop="deleteInvoiceFromPool(invoice)"
                  >
                    <X class="h-3.5 w-3.5" />
                  </button>
                </div>
              </article>
            </div>
          </div>
        </div>
      </div>
    </section>

    <input ref="transactionInputRef" class="hidden" type="file" accept="image/*" multiple @change="handleTransactionFiles" />

    <section class="tool-panel overflow-hidden rounded-lg">
      <div class="flex items-center justify-between border-b border-slate-200 px-5 py-4">
        <div>
          <h2 class="section-title">报销记录</h2>
          <p class="muted mt-1">已形成的报销记录。</p>
        </div>
      </div>

      <div v-if="loading" class="px-5 py-12 text-center text-sm text-slate-500">加载中...</div>
      <div v-else-if="!formedExpenses.length" class="empty-state">
        <div class="empty-state-icon"><CheckCircle2 class="h-6 w-6" /></div>
        <div>
          <div class="text-sm font-medium text-slate-700">暂无报销记录</div>
          <div class="mt-1 text-xs text-slate-500">提交后会出现在这里。</div>
        </div>
      </div>

      <div v-else class="overflow-x-auto">
        <table class="min-w-full divide-y divide-slate-200 text-left text-sm">
          <thead class="bg-slate-50 text-xs font-medium uppercase tracking-normal text-slate-500">
            <tr>
              <th class="px-5 py-3">项目</th>
              <th class="px-5 py-3">月份</th>
              <th class="px-5 py-3">类别</th>
              <th class="px-5 py-3">金额</th>
              <th class="px-5 py-3">发票</th>
              <th class="px-5 py-3">替票</th>
              <th class="px-5 py-3">操作</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100 bg-white">
            <tr v-for="expense in formedExpenses" :key="expense.id" class="hover:bg-slate-50/70">
              <td class="px-5 py-4 font-medium text-slate-900">{{ expense.project_name || expense.category }}</td>
              <td class="px-5 py-4 text-slate-600">{{ expense.expense_month }}</td>
              <td class="px-5 py-4 text-slate-600">{{ expense.category }}</td>
              <td class="px-5 py-4 font-medium text-slate-900">{{ formatCurrency(expense.actual_amount) }}</td>
              <td class="px-5 py-4 text-slate-600">{{ expense.allocation_count }} 张</td>
              <td class="px-5 py-4">
                <span class="status-pill" :class="expense.is_substitute ? 'bg-amber-50 text-amber-700' : 'bg-slate-100 text-slate-600'">
                  {{ expense.is_substitute ? "是" : "否" }}
                </span>
              </td>
              <td class="px-5 py-4">
                <div class="flex items-center gap-2">
                  <button class="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-teal-700" type="button" @click="triggerTransactionUpload(expense)">
                    <ImagePlus class="h-3.5 w-3.5" /> 补材料
                  </button>
                  <button class="secondary-button h-8 px-2 text-xs" type="button" @click="handleWithdraw(expense)">撤回</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>
