<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { CheckCircle2, ImagePlus, Link2, Loader2, PlusCircle, ReceiptText } from "lucide-vue-next";
import AttachmentThumb from "../components/AttachmentThumb.vue";
import InvoiceUploadPanel from "../components/InvoiceUploadPanel.vue";
import { DEFAULT_EXPENSE_CATEGORY, EXPENSE_CATEGORIES } from "../constants/expenseCategories";
import {
  createExpenseAllocation,
  createExpenseDraft,
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

const selectedExpenseId = ref<number | null>(props.draftExpense?.id ?? null);
const selectedInvoiceKey = ref("");
const allocationAmount = ref("");
const allocationNote = ref("");

const expenseForm = reactive({
  project_name: "",
  actual_amount: "",
  expense_month: currentReimbursementMonth(),
  category: DEFAULT_EXPENSE_CATEGORY
});

const selectedExpense = computed(() => expenses.value.find((item) => item.id === selectedExpenseId.value) ?? null);
const selectedInvoice = computed(() => invoicePool.value.find((item) => invoiceKey(item) === selectedInvoiceKey.value) ?? null);
const pendingExpenses = computed(() => expenses.value.filter((item) => item.remaining_amount > 0 || item.status === "draft"));
const usableInvoices = computed(() => invoicePool.value.filter((item) => item.remaining_amount > 0));
const matchReady = computed(() => Boolean(selectedExpense.value && selectedInvoice.value && Number(allocationAmount.value) > 0));

function invoiceKey(item: InvoicePoolItem): string {
  return `${item.attachment_id}:${item.invoice_item_index}`;
}

function allocationDefault(expense: Expense | null, invoice: InvoicePoolItem | null): string {
  if (!expense || !invoice) return "";
  const amount = Math.min(expense.remaining_amount || expense.actual_amount, invoice.remaining_amount);
  return amount > 0 ? String(amount) : "";
}

function statusLabel(expense: Expense): string {
  if (expense.status === "submitted") return "已提交";
  if (expense.allocated_amount > 0) return "部分匹配";
  return "待补票";
}

function invoiceStatusLabel(invoice: InvoicePoolItem): string {
  if (invoice.remaining_amount <= 0) return "已用完";
  if (invoice.allocated_amount > 0) return "部分使用";
  return "待匹配";
}

function selectExpense(expense: Expense) {
  selectedExpenseId.value = expense.id;
  allocationAmount.value = allocationDefault(expense, selectedInvoice.value);
}

function selectInvoice(invoice: InvoicePoolItem) {
  selectedInvoiceKey.value = invoiceKey(invoice);
  allocationAmount.value = allocationDefault(selectedExpense.value, invoice);
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

function removeUploaded(id: number) {
  const removed = uploadedAttachments.value.find((item) => item.id === id);
  if (removed?.preview_url) URL.revokeObjectURL(removed.preview_url);
  uploadedAttachments.value = uploadedAttachments.value.filter((item) => item.id !== id);
}

async function matchSelected() {
  const expense = selectedExpense.value;
  const invoice = selectedInvoice.value;
  const amount = Number(allocationAmount.value);
  if (!expense || !invoice || !amount || amount <= 0) {
    error.value = "请选择花费和发票，并填写分摊金额。";
    return;
  }
  if (amount > expense.remaining_amount) {
    error.value = "分摊金额不能超过花费待覆盖金额。";
    return;
  }
  if (amount > invoice.remaining_amount) {
    error.value = "分摊金额不能超过发票可用金额。";
    return;
  }

  matching.value = true;
  error.value = "";
  success.value = "";
  try {
    const updated = await createExpenseAllocation({
      expense_id: expense.id,
      attachment_id: invoice.attachment_id,
      invoice_item_index: invoice.invoice_item_index,
      allocated_amount: amount,
      note: allocationNote.value.trim()
    });
    await loadWorkspace();
    selectedExpenseId.value = updated.remaining_amount > 0 ? updated.id : null;
    selectedInvoiceKey.value = "";
    allocationAmount.value = "";
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

watch([selectedExpense, selectedInvoice], ([expense, invoice]) => {
  allocationAmount.value = allocationDefault(expense, invoice);
});

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

      <InvoiceUploadPanel :attachments="uploadedAttachments" @uploaded="handleUploaded" @remove="removeUploaded" />
    </div>

    <!-- 匹配区 -->
    <section class="tool-panel rounded-lg">
      <div class="border-b border-slate-200 px-5 py-4">
        <h2 class="section-title">匹配区</h2>
        <p class="muted mt-1">从下方选择花费和发票，在这里完成关联。</p>
      </div>
      <div class="match-flow">
        <!-- 花费节点 -->
        <div class="match-node">
          <div :class="selectedExpense ? 'match-bullet-selected' : 'match-bullet-empty'">
            <PlusCircle class="h-6 w-6" />
          </div>
          <div class="w-full">
            <div class="text-xs font-medium text-slate-500">花费</div>
            <div class="mt-0.5 truncate text-sm font-semibold text-ink">
              {{ selectedExpense?.project_name || "未选择" }}
            </div>
            <div v-if="selectedExpense" class="mt-0.5 text-xs text-teal-700">
              待覆盖 {{ formatCurrency(selectedExpense.remaining_amount) }}
            </div>
            <div v-else class="mt-0.5 text-xs text-slate-400">从花费池点选</div>
          </div>
        </div>

        <!-- 左连线 -->
        <div class="match-connector">
          <div :class="selectedExpense ? 'match-connector-active' : 'match-connector-line'" />
        </div>

        <!-- 中间：分摊表单 -->
        <div class="match-center">
          <div>
            <label class="field-label" for="allocated-amount">分摊金额</label>
            <input id="allocated-amount" v-model="allocationAmount" class="field-input mt-1" inputmode="decimal" />
          </div>
          <div>
            <label class="field-label" for="allocation-note">说明</label>
            <textarea id="allocation-note" v-model="allocationNote" class="field-textarea mt-1" rows="2" placeholder="替票、分摊原因等" />
          </div>
          <button class="primary-button w-full" type="button" :disabled="matching || !matchReady" @click="matchSelected">
            <Link2 class="h-4 w-4" />
            {{ matching ? "正在匹配..." : "保存匹配" }}
          </button>
        </div>

        <!-- 右连线 -->
        <div class="match-connector">
          <div :class="selectedInvoice ? 'match-connector-active' : 'match-connector-line'" />
        </div>

        <!-- 发票节点 -->
        <div class="match-node">
          <div :class="selectedInvoice ? 'match-bullet-selected' : 'match-bullet-empty'">
            <ReceiptText class="h-6 w-6" />
          </div>
          <div class="w-full">
            <div class="text-xs font-medium text-slate-500">发票</div>
            <div class="mt-0.5 truncate text-sm font-semibold text-ink">
              {{ selectedInvoice?.invoice_type || "未选择" }}
            </div>
            <div v-if="selectedInvoice" class="mt-0.5 text-xs text-teal-700">
              可用 {{ formatCurrency(selectedInvoice.remaining_amount) }}
            </div>
            <div v-else class="mt-0.5 text-xs text-slate-400">从发票池点选</div>
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
            role="button"
            tabindex="0"
            @click="selectExpense(expense)"
            @keydown.enter.prevent="selectExpense(expense)"
          >
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <div class="truncate text-sm font-semibold text-ink">{{ expense.project_name || expense.category }}</div>
                <div class="mt-1 text-xs text-slate-500">{{ expense.expense_month }} · {{ expense.category }}</div>
              </div>
              <span class="status-pill shrink-0" :class="expense.status === 'submitted' ? 'bg-teal-50 text-teal-700' : 'bg-amber-50 text-amber-700'">
                {{ statusLabel(expense) }}
              </span>
            </div>
            <div class="grid gap-1.5 text-xs text-slate-500">
              <div>金额：<span class="font-medium text-slate-800">{{ formatCurrency(expense.actual_amount) }}</span></div>
              <div>已覆盖：<span class="font-medium text-slate-800">{{ formatCurrency(expense.allocated_amount) }}</span></div>
            </div>
            <div class="mt-auto flex flex-wrap items-center gap-2">
              <div
                v-for="attachment in expense.attachments.slice(0, 2)"
                :key="attachment.id"
                class="inline-flex max-w-full items-center gap-1.5 rounded-md bg-slate-100 px-2 py-1 text-xs text-slate-600"
              >
                <AttachmentThumb :attachment="attachment" />
                <span class="truncate">{{ attachment.original_filename }}</span>
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
          <p class="muted mt-1">点击选中后去匹配区关联花费。允许一张发票分摊给多条花费。</p>
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
          <button
            v-for="invoice in usableInvoices"
            :key="invoiceKey(invoice)"
            class="flex flex-col gap-3 rounded-lg border p-4 text-left transition hover:border-teal-300 hover:shadow-sm"
            :class="selectedInvoiceKey === invoiceKey(invoice) ? 'border-teal-400 bg-teal-50/60 ring-2 ring-teal-700/10' : 'border-slate-200 bg-white'"
            type="button"
            @click="selectInvoice(invoice)"
          >
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <div class="truncate text-sm font-semibold text-ink">{{ invoice.invoice_type }}</div>
                <div class="mt-1 truncate text-xs text-slate-500">{{ invoice.attachment_name }}</div>
              </div>
              <span class="status-pill shrink-0" :class="invoice.allocated_amount ? 'bg-amber-50 text-amber-700' : 'bg-slate-100 text-slate-600'">
                {{ invoiceStatusLabel(invoice) }}
              </span>
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
          </button>
        </div>
      </section>
    </div>
  </div>
</template>
