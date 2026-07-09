<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { CheckCircle2, Loader2, PlusCircle, ReceiptText, Trash2, X } from "lucide-vue-next";
import InvoiceUploadPanel from "../components/InvoiceUploadPanel.vue";
import { buyerMatchStatus, isDifferentAllowedBuyer } from "../constants/companyEntities";
import { DEFAULT_EXPENSE_CATEGORY, EXPENSE_CATEGORIES } from "../constants/expenseCategories";
import {
  addAttachmentsToInvoicePool,
  createExpenseDraft,
  deleteAttachment,
  deleteExpense,
  listExpenses,
  listInvoicePool,
} from "../services/api";
import { currentReimbursementMonth, formatCurrency, formatDate } from "../utils/format";
import type { Attachment, Expense, ExpenseCreatePayload, InvoicePoolItem, User } from "../types";

const props = defineProps<{
  user: User;
  refreshKey: number;
}>();

const emit = defineEmits<{
  refreshed: [];
}>();

const expenses = ref<Expense[]>([]);
const invoicePool = ref<InvoicePoolItem[]>([]);
const uploadedAttachments = ref<Attachment[]>([]);
const selectedExpenseId = ref<number | null>(null);
const selectedInvoiceKeys = ref<string[]>([]);
const loading = ref(false);
const saving = ref(false);
const pooling = ref(false);
const deletingExpenseId = ref<number | null>(null);
const deletingAttachmentId = ref<number | null>(null);
const error = ref("");
const success = ref("");

const draftForm = ref({
  project_name: "",
  actual_amount: "",
  expense_month: currentReimbursementMonth(),
  category: DEFAULT_EXPENSE_CATEGORY,
});

const draftExpenses = computed(() => expenses.value.filter((e) => e.status === "pending"));
const usableInvoices = computed(() => invoicePool.value.filter((i) => i.remaining_amount > 0));
const selectedExpense = computed(() =>
  draftExpenses.value.find((expense) => expense.id === selectedExpenseId.value) ?? null
);
const selectedInvoices = computed(() =>
  usableInvoices.value.filter((item) => selectedInvoiceKeys.value.includes(invoiceKey(item)))
);
const selectedInvoiceTotal = computed(() =>
  selectedInvoices.value.reduce((sum, item) => sum + Number(item.invoice_amount), 0)
);
const selectedOutcome = computed(() => {
  if (!selectedExpense.value || !selectedInvoices.value.length) return "";
  return selectedInvoiceTotal.value === Number(selectedExpense.value.actual_amount) ? "真实票" : "替票";
});

function invoiceKey(item: InvoicePoolItem): string {
  return `${item.attachment_id}:${item.invoice_item_index}`;
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

function stagedInvoiceRefs(attachments: Attachment[]) {
  return attachments.flatMap((attachment) =>
    (Array.isArray(attachment.ocr_result.invoice_items) ? attachment.ocr_result.invoice_items as Array<Record<string, unknown>> : [])
      .map((item, index) => ({ item, index }))
      .filter(({ item }) => typeof item.amount === "number" && item.amount > 0)
      .map(({ item, index }) => ({
        attachment_id: attachment.id,
        invoice_item_index: index,
        invoice_amount: Number(item.amount),
      }))
  );
}

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

function resetDraftForm() {
  draftForm.value = {
    project_name: "",
    actual_amount: "",
    expense_month: currentReimbursementMonth(),
    category: DEFAULT_EXPENSE_CATEGORY,
  };
}

async function saveDraft() {
  const data: ExpenseCreatePayload = {
    project_name: draftForm.value.project_name.trim(),
    actual_amount: Number(draftForm.value.actual_amount),
    expense_month: draftForm.value.expense_month,
    category: draftForm.value.category,
  };
  if (!data.project_name) { error.value = "请填写报销事项"; return; }
  if (!data.actual_amount || data.actual_amount <= 0) { error.value = "请填写金额"; return; }

  saving.value = true;
  error.value = "";
  success.value = "";
  try {
    const created = await createExpenseDraft(data);
    selectedExpenseId.value = created.id;
    resetDraftForm();
    await load();
    success.value = "已保存到待补材料";
  } catch (err) {
    error.value = err instanceof Error ? err.message : "保存失败";
  } finally {
    saving.value = false;
  }
}

async function handleUploaded(attachments: Attachment[]) {
  if (!attachments.length) return;
  uploadedAttachments.value = [...attachments, ...uploadedAttachments.value];
  await addUploadedToPool();
}

async function addUploadedToPool() {
  if (!uploadedAttachments.value.length) return;
  const refs = stagedInvoiceRefs(uploadedAttachments.value);
  if (!refs.length) { error.value = "未识别到可入池的票据条目"; return; }

  pooling.value = true;
  error.value = "";
  success.value = "";
  try {
    await addAttachmentsToInvoicePool(uploadedAttachments.value.map((a) => a.id));
    uploadedAttachments.value = [];
    await load();
    success.value = "发票已加入待补材料";
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
    uploadedAttachments.value = uploadedAttachments.value.filter((a) => a.id !== id);
    await load();
    success.value = "发票已删除";
  } catch (err) {
    error.value = err instanceof Error ? err.message : "删除失败";
  } finally {
    deletingAttachmentId.value = null;
  }
}

async function handleDeleteExpense(expense: Expense) {
  if (!window.confirm(`删除「${expense.project_name}」？不可恢复。`)) return;
  deletingExpenseId.value = expense.id;
  try {
    await deleteExpense(expense.id);
    if (selectedExpenseId.value === expense.id) selectedExpenseId.value = null;
    await load();
    success.value = "草稿已删除";
  } catch (err) {
    error.value = err instanceof Error ? err.message : "删除失败";
  } finally {
    deletingExpenseId.value = null;
  }
}

async function deleteInvoiceFromPool(invoice: InvoicePoolItem) {
  if (!window.confirm(`删除发票「${invoice.attachment_name}」？`)) return;
  deletingAttachmentId.value = invoice.attachment_id;
  try {
    await deleteAttachment(invoice.attachment_id);
    selectedInvoiceKeys.value = selectedInvoiceKeys.value.filter((key) => !key.startsWith(`${invoice.attachment_id}:`));
    await load();
    success.value = "发票已删除";
  } catch (err) {
    error.value = err instanceof Error ? err.message : "删除失败";
  } finally {
    deletingAttachmentId.value = null;
  }
}

function toggleExpense(expense: Expense) {
  selectedExpenseId.value = selectedExpenseId.value === expense.id ? null : expense.id;
}

function toggleInvoice(invoice: InvoicePoolItem) {
  const key = invoiceKey(invoice);
  selectedInvoiceKeys.value = selectedInvoiceKeys.value.includes(key)
    ? selectedInvoiceKeys.value.filter((item) => item !== key)
    : [...selectedInvoiceKeys.value, key];
}

onMounted(load);
watch(() => props.refreshKey, load);
</script>

<template>
  <div class="mx-auto max-w-7xl space-y-5">
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 class="page-title">待补材料</h1>
        <p class="muted mt-1">随手记一笔，或先把发票放进来。</p>
      </div>
      <div class="grid grid-cols-2 gap-2 text-right text-xs text-slate-500">
        <div class="rounded-md border border-slate-200 bg-white px-3 py-2">
          <div>报销草稿</div>
          <strong class="mt-1 block text-base text-ink">{{ draftExpenses.length }}</strong>
        </div>
        <div class="rounded-md border border-slate-200 bg-white px-3 py-2">
          <div>未归属发票</div>
          <strong class="mt-1 block text-base text-ink">{{ usableInvoices.length }}</strong>
        </div>
      </div>
    </div>

    <p v-if="error" class="rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-700">{{ error }}</p>
    <p v-if="success" class="rounded-md bg-teal-50 px-3 py-2 text-sm text-teal-800">{{ success }}</p>

    <section class="grid gap-5 xl:grid-cols-[minmax(0,0.92fr)_minmax(420px,1.08fr)]">
      <div class="tool-panel overflow-hidden rounded-lg">
        <div class="border-b border-slate-200 px-5 py-4">
          <h2 class="section-title">随手记一笔</h2>
        </div>
        <div class="space-y-4 p-5">
          <div class="grid gap-3 sm:grid-cols-2">
            <div class="sm:col-span-2">
              <label class="field-label" for="draft-project">报销事项</label>
              <input id="draft-project" v-model="draftForm.project_name" class="field-input mt-1" placeholder="如：客户拜访打车" />
            </div>
            <div>
              <label class="field-label" for="draft-amount">金额</label>
              <input id="draft-amount" v-model="draftForm.actual_amount" class="field-input mt-1" inputmode="decimal" />
            </div>
            <div>
              <label class="field-label" for="draft-month">月份</label>
              <input id="draft-month" v-model="draftForm.expense_month" class="field-input mt-1" type="month" />
            </div>
            <div class="sm:col-span-2">
              <label class="field-label" for="draft-category">类别</label>
              <select id="draft-category" v-model="draftForm.category" class="field-input mt-1">
                <option v-for="cat in EXPENSE_CATEGORIES" :key="cat">{{ cat }}</option>
              </select>
            </div>
          </div>
          <button
            class="primary-button w-full"
            type="button"
            :disabled="saving || !draftForm.project_name.trim() || Number(draftForm.actual_amount) <= 0"
            @click="saveDraft"
          >
            <Loader2 v-if="saving" class="h-4 w-4 animate-spin" />
            <PlusCircle v-else class="h-4 w-4" />
            保存草稿
          </button>
        </div>
      </div>

      <div class="tool-panel overflow-hidden rounded-lg">
        <div class="border-b border-slate-200 px-5 py-4">
          <h2 class="section-title">单独传发票</h2>
        </div>
        <div class="p-5">
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
      </div>
    </section>

    <section class="tool-panel overflow-hidden rounded-lg">
      <div class="flex items-center justify-between border-b border-slate-200 px-5 py-4">
        <div>
          <h2 class="section-title">补齐材料</h2>
          <p class="muted mt-1">选择一条草稿，再选择发票。</p>
        </div>
        <div v-if="selectedExpense && selectedInvoices.length" class="text-right">
          <div class="text-xs text-slate-400">归属结果</div>
          <div class="text-sm font-semibold" :class="selectedOutcome === '替票' ? 'text-amber-700' : 'text-teal-700'">
            {{ selectedOutcome }}
          </div>
        </div>
      </div>

      <div v-if="loading" class="px-5 py-12 text-center text-sm text-slate-500">加载中...</div>
      <div v-else-if="!draftExpenses.length && !usableInvoices.length" class="empty-state">
        <div class="empty-state-icon"><CheckCircle2 class="h-6 w-6" /></div>
        <div>
          <div class="text-sm font-medium text-slate-700">暂无待补材料</div>
          <div class="mt-1 text-xs text-slate-500">随手记或上传发票后会出现在这里。</div>
        </div>
      </div>

      <div v-else class="grid gap-5 p-5 lg:grid-cols-2">
        <div>
          <div class="mb-3 text-xs font-semibold uppercase tracking-normal text-slate-400">报销草稿</div>
          <div v-if="!draftExpenses.length" class="match-empty-copy">
            <ReceiptText class="h-5 w-5 text-slate-400" />
            <span>暂无草稿</span>
          </div>
          <div v-else class="space-y-2">
            <article
              v-for="expense in draftExpenses"
              :key="expense.id"
              class="cursor-pointer rounded-md border px-3 py-3 transition"
              :class="selectedExpenseId === expense.id ? 'border-teal-400 bg-teal-50/60 ring-2 ring-teal-700/10' : 'border-slate-200 bg-white hover:border-teal-300'"
              @click="toggleExpense(expense)"
            >
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <div class="truncate text-sm font-semibold text-ink">{{ expense.project_name || expense.category }}</div>
                  <div class="mt-1 text-xs text-slate-500">{{ expense.expense_month }} · {{ expense.category }}</div>
                </div>
                <div class="flex shrink-0 items-center gap-2">
                  <span class="text-sm font-semibold text-ink">{{ formatCurrency(expense.actual_amount) }}</span>
                  <button
                    class="grid h-7 w-7 place-items-center rounded-md text-slate-400 transition hover:bg-rose-50 hover:text-rose-700"
                    type="button"
                    :disabled="deletingExpenseId === expense.id"
                    @click.stop="handleDeleteExpense(expense)"
                  >
                    <Loader2 v-if="deletingExpenseId === expense.id" class="h-4 w-4 animate-spin" />
                    <Trash2 v-else class="h-4 w-4" />
                  </button>
                </div>
              </div>
            </article>
          </div>
        </div>

        <div>
          <div class="mb-3 text-xs font-semibold uppercase tracking-normal text-slate-400">未归属发票</div>
          <div v-if="!usableInvoices.length" class="match-empty-copy">
            <ReceiptText class="h-5 w-5 text-slate-400" />
            <span>暂无发票</span>
          </div>
          <div v-else class="space-y-2">
            <article
              v-for="invoice in usableInvoices"
              :key="invoiceKey(invoice)"
              class="cursor-pointer rounded-md border px-3 py-3 transition"
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
              <div class="mt-2 flex items-center justify-between gap-3 text-xs">
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
                <div class="flex items-center gap-2">
                  <span class="text-slate-400">{{ invoice.invoice_date || formatDate(invoice.created_at) }}</span>
                  <button
                    class="text-slate-300 hover:text-rose-600"
                    type="button"
                    :disabled="deletingAttachmentId === invoice.attachment_id"
                    @click.stop="deleteInvoiceFromPool(invoice)"
                  >
                    <X class="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            </article>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>
