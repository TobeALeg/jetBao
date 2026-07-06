<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { AlertTriangle, CheckCircle2, ImagePlus, Link2, Loader2, PlusCircle, ReceiptText, Trash2, X } from "lucide-vue-next";
import AttachmentThumb from "../components/AttachmentThumb.vue";
import InvoiceUploadPanel from "../components/InvoiceUploadPanel.vue";
import { DEFAULT_EXPENSE_CATEGORY, EXPENSE_CATEGORIES } from "../constants/expenseCategories";
import {
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
const matching = ref(false);
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

const selectedExpense = computed(() => expenses.value.find((item) => item.id === selectedExpenseId.value) ?? null);
const selectedInvoices = computed(() => invoicePool.value.filter((item) => selectedInvoiceKeys.value.includes(invoiceKey(item))));
const selectedInvoiceTotal = computed(() => selectedInvoices.value.reduce((sum, item) => sum + Number(item.invoice_amount), 0));
const totalAfterMatch = computed(() => {
  const expense = selectedExpense.value;
  if (!expense) return 0;
  return Number(expense.allocated_amount) + selectedInvoiceTotal.value;
});
const matchDifference = computed(() => {
  const expense = selectedExpense.value;
  if (!expense) return 0;
  return totalAfterMatch.value - Number(expense.actual_amount);
});
const remainingAfterMatch = computed(() => Math.max(Math.abs(matchDifference.value), 0));
const matchProgress = computed(() => {
  const expense = selectedExpense.value;
  if (!expense || Number(expense.actual_amount) <= 0) return 0;
  return Math.min((totalAfterMatch.value / Number(expense.actual_amount)) * 100, 100);
});
const needsMismatchNote = computed(() => matchDifference.value > 0);
const pendingExpenses = computed(() => expenses.value.filter((item) => item.remaining_amount > 0 || item.status === "draft"));
const usableInvoices = computed(() => invoicePool.value.filter((item) => item.remaining_amount > 0));
const matchReady = computed(() => Boolean(selectedExpense.value && selectedInvoices.value.length > 0 && (!needsMismatchNote.value || allocationNote.value.trim())));
const matchStateLabel = computed(() => {
  if (!selectedExpense.value) return "先选择一条花费";
  if (!selectedInvoices.value.length) return "再选择发票";
  if (matchDifference.value > 0) return `超出 ${formatCurrency(remainingAfterMatch.value)}`;
  if (matchDifference.value < 0) return `还差 ${formatCurrency(remainingAfterMatch.value)}`;
  return "刚好匹配";
});
const matchStateTone = computed(() => {
  if (!selectedExpense.value || !selectedInvoices.value.length) return "neutral";
  if (matchDifference.value > 0) return "warning";
  if (matchDifference.value < 0) return "partial";
  return "complete";
});
const matchActionLabel = computed(() => {
  if (matching.value) return "正在匹配...";
  if (!selectedExpense.value || !selectedInvoices.value.length) return "选择后保存";
  if (matchDifference.value > 0) return "保存为替票";
  if (matchDifference.value < 0) return "保存部分匹配";
  return "完成匹配";
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

async function submitExpense(payload?: DraftExpenseCreatePayload) {
  const data = payload ?? {
    project_name: expenseForm.project_name.trim(),
    actual_amount: Number(expenseForm.actual_amount),
    expense_month: expenseForm.expense_month,
    category: expenseForm.category
  };
  if (!data.project_name) {
    error.value = "请填写项目名称。";
    return;
  }
  if (!data.actual_amount || data.actual_amount <= 0) {
    error.value = "请填写金额。";
    return;
  }

  savingExpense.value = true;
  error.value = "";
  success.value = "";
  try {
    const created = await createExpenseDraft(data);
    expenseForm.project_name = "";
    expenseForm.actual_amount = "";
    expenseForm.category = DEFAULT_EXPENSE_CATEGORY;
    await loadWorkspace();
    selectedExpenseId.value = created.id;
    success.value = "花费项目已加入待定池";
  } catch (err) {
    error.value = err instanceof Error ? err.message : "保存失败";
  } finally {
    savingExpense.value = false;
  }
}

async function handleUploaded(attachment: Attachment) {
  uploadedAttachments.value = [attachment, ...uploadedAttachments.value];
  await loadWorkspace();
  const firstNewInvoice = invoicePool.value.find((item) => item.attachment_id === attachment.id && item.remaining_amount > 0);
  if (firstNewInvoice) selectInvoice(firstNewInvoice);
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

async function matchSelected() {
  const expense = selectedExpense.value;
  const invoices = selectedInvoices.value;
  if (!expense || !invoices.length) {
    error.value = "请选择一条花费和至少一张发票。";
    return;
  }
  if (needsMismatchNote.value && !allocationNote.value.trim()) {
    error.value = "票面合计超过花费金额时必须填写说明。";
    return;
  }

  matching.value = true;
  error.value = "";
  success.value = "";
  try {
    const updated = await createExpenseAllocationsBatch({
      expense_id: expense.id,
      invoices: invoices.map((invoice) => ({
        attachment_id: invoice.attachment_id,
        invoice_item_index: invoice.invoice_item_index
      })),
      note: allocationNote.value.trim()
    });
    await loadWorkspace();
    selectedExpenseId.value = updated.remaining_amount > 0 ? updated.id : null;
    selectedInvoiceKeys.value = [];
    allocationNote.value = "";
    success.value = updated.remaining_amount > 0 ? "已保存部分匹配" : "已匹配完成";
    if (updated.remaining_amount <= 0) emit("submitted");
  } catch (err) {
    error.value = err instanceof Error ? err.message : "匹配失败";
  } finally {
    matching.value = false;
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
      <p class="muted mt-1">左侧记花费，右侧传发票，然后在匹配区将它们关联起来。</p>
    </div>

    <p v-if="error" class="rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-700">{{ error }}</p>
    <p v-if="success" class="rounded-md bg-teal-50 px-3 py-2 text-sm text-teal-800">{{ success }}</p>

    <!-- 录入区：花费表单 ‖ 发票上传，等高并排 -->
    <div class="grid gap-5 xl:grid-cols-2">
      <section class="tool-panel flex flex-col rounded-lg">
        <div class="border-b border-slate-200 px-5 py-4">
          <h2 class="section-title">记一笔花费</h2>
          <p class="muted mt-1">填写项目信息，加入花费待定池。</p>
        </div>
        <form class="grid flex-1 gap-3 content-start p-5 lg:grid-cols-2" @submit.prevent="submitExpense()">
          <div class="lg:col-span-2">
            <label class="field-label" for="expense-project">项目名称</label>
            <input id="expense-project" v-model="expenseForm.project_name" class="field-input mt-1" placeholder="如：客户拜访打车" />
          </div>
          <div>
            <label class="field-label" for="expense-amount">金额</label>
            <input id="expense-amount" v-model="expenseForm.actual_amount" class="field-input mt-1" inputmode="decimal" />
          </div>
          <div>
            <label class="field-label">月份</label>
            <div class="mt-1 flex h-10 items-center rounded-md border border-slate-200 bg-slate-50 px-3 text-sm text-slate-700">
              {{ expenseForm.expense_month }}
            </div>
          </div>
          <div>
            <label class="field-label" for="expense-category">类别</label>
            <select id="expense-category" v-model="expenseForm.category" class="field-input mt-1">
              <option v-for="category in EXPENSE_CATEGORIES" :key="category">{{ category }}</option>
            </select>
          </div>
          <div class="flex items-end">
            <button class="primary-button w-full" type="submit" :disabled="savingExpense">
              <PlusCircle class="h-4 w-4" />
              {{ savingExpense ? "正在加入..." : "加入花费池" }}
            </button>
          </div>
        </form>
      </section>

      <InvoiceUploadPanel
        :attachments="uploadedAttachments"
        :removing-id="deletingAttachmentId"
        @uploaded="handleUploaded"
        @remove="removeUploaded"
      />
    </div>

    <!-- 匹配区 -->
    <section class="tool-panel overflow-hidden rounded-lg">
      <div class="flex flex-col gap-3 border-b border-slate-200 px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h2 class="section-title">匹配篮</h2>
          <p class="muted mt-1">选择一条花费，把发票放进篮子里核对金额。</p>
        </div>
        <div
          class="inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-medium"
          :class="{
            'bg-slate-100 text-slate-600': matchStateTone === 'neutral',
            'bg-teal-50 text-teal-700': matchStateTone === 'complete',
            'bg-amber-50 text-amber-700': matchStateTone === 'warning',
            'bg-sky-50 text-sky-700': matchStateTone === 'partial'
          }"
        >
          <CheckCircle2 v-if="matchStateTone === 'complete'" class="h-3.5 w-3.5" />
          <AlertTriangle v-else-if="matchStateTone === 'warning'" class="h-3.5 w-3.5" />
          <ReceiptText v-else class="h-3.5 w-3.5" />
          {{ matchStateLabel }}
        </div>
      </div>

      <div class="match-workbench">
        <div class="match-expense-panel">
          <div class="flex items-center justify-between gap-3">
            <div class="text-xs font-semibold uppercase tracking-normal text-slate-400">当前花费</div>
            <span v-if="selectedExpense" class="status-pill bg-slate-100 text-slate-600">{{ selectedExpense.category }}</span>
          </div>
          <div v-if="selectedExpense" class="mt-4 space-y-4">
            <div>
              <div class="truncate text-lg font-semibold text-ink">{{ selectedExpense.project_name || selectedExpense.category }}</div>
              <div class="mt-1 text-xs text-slate-500">{{ selectedExpense.expense_month }} · {{ selectedExpense.attachments.length }} 个交易附件</div>
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
          </div>
          <div v-else class="match-empty-copy">
            <PlusCircle class="h-7 w-7 text-slate-300" />
            <span>从下方花费池选择一条记录。</span>
          </div>
        </div>

        <div class="match-meter-panel">
          <div class="flex items-start justify-between gap-4">
            <div>
              <div class="text-xs font-semibold uppercase tracking-normal text-slate-400">金额核对</div>
              <div class="mt-2 text-2xl font-semibold text-ink">{{ formatCurrency(totalAfterMatch) }}</div>
              <div class="mt-1 text-xs text-slate-500">当前已匹配 + 本次已选发票</div>
            </div>
            <div class="text-right text-xs text-slate-500">
              <div>目标金额</div>
              <div class="mt-1 text-base font-semibold text-ink">{{ selectedExpense ? formatCurrency(selectedExpense.actual_amount) : "-" }}</div>
            </div>
          </div>

          <div class="mt-5">
            <div class="match-progress-track">
              <div
                class="match-progress-fill"
                :class="needsMismatchNote ? 'bg-amber-500' : 'bg-teal-600'"
                :style="{ width: `${matchProgress}%` }"
              />
            </div>
            <div class="mt-2 flex justify-between text-xs text-slate-500">
              <span>{{ selectedInvoices.length }} 张发票</span>
              <span>{{ selectedExpense ? matchStateLabel : "等待选择" }}</span>
            </div>
          </div>

          <div class="mt-5 grid gap-2 text-xs sm:grid-cols-3">
            <div class="match-mini-stat">
              <span>本次发票</span>
              <strong>{{ formatCurrency(selectedInvoiceTotal) }}</strong>
            </div>
            <div class="match-mini-stat">
              <span>匹配后差额</span>
              <strong :class="matchDifference > 0 ? 'text-amber-700' : 'text-ink'">
                {{ selectedExpense ? formatCurrency(matchDifference) : "-" }}
              </strong>
            </div>
            <div class="match-mini-stat">
              <span>动作</span>
              <strong>{{ matchActionLabel }}</strong>
            </div>
          </div>

          <div class="mt-5">
            <label class="field-label" for="allocation-note">说明</label>
            <textarea
              id="allocation-note"
              v-model="allocationNote"
              class="field-textarea mt-1 min-h-20"
              rows="2"
              :placeholder="needsMismatchNote ? '说明为什么使用大额发票替票' : '可填写匹配说明'"
            />
            <p v-if="needsMismatchNote" class="mt-1 text-xs text-amber-700">票面合计超过花费金额，保存后会标记为替票。</p>
          </div>

          <button class="primary-button mt-4 w-full" type="button" :disabled="matching || !matchReady" @click="matchSelected">
            <Loader2 v-if="matching" class="h-4 w-4 animate-spin" />
            <Link2 v-else class="h-4 w-4" />
            {{ matchActionLabel }}
          </button>
        </div>

        <div class="match-basket-panel">
          <div class="flex items-center justify-between gap-3">
            <div class="text-xs font-semibold uppercase tracking-normal text-slate-400">发票篮</div>
            <span class="status-pill bg-teal-50 text-teal-700">{{ selectedInvoices.length }} 张</span>
          </div>
          <div v-if="selectedInvoices.length" class="mt-4 space-y-2">
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
          <div v-else class="match-empty-copy">
            <ReceiptText class="h-7 w-7 text-slate-300" />
            <span>从下方发票池点选一张或多张发票。</span>
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
          <p class="muted mt-1">点击选中后去匹配区关联发票。</p>
        </div>

        <div v-if="loading" class="px-5 py-10 text-center text-sm text-slate-500">正在加载...</div>
        <div v-else-if="!pendingExpenses.length" class="empty-state">
          <div class="empty-state-icon">
            <PlusCircle class="h-6 w-6" />
          </div>
          <div>
            <div class="text-sm font-medium text-slate-700">花费池为空</div>
            <div class="mt-1 text-xs text-slate-500">在上方表单填写项目名称和金额，将花费加入待定池。</div>
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
            <div class="mt-1 text-xs text-slate-500">先在上方「发票附件」区域上传发票 PDF 或图片。</div>
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
              <span class="truncate">{{ invoice.invoice_buyer || "未识别抬头" }}</span>
              <CheckCircle2 v-if="invoice.invoice_buyer && invoice.invoice_buyer.includes(user.company_entity)" class="h-3.5 w-3.5 shrink-0 text-teal-700" />
            </div>
          </article>
        </div>
      </section>
    </div>
  </div>
</template>
