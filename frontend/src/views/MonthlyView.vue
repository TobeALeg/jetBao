<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { CheckCircle2, FilePlus2, ImagePlus, Loader2, Plus, X } from "lucide-vue-next";
import { buyerMatchStatus, isDifferentAllowedBuyer } from "../constants/companyEntities";
import { DEFAULT_EXPENSE_CATEGORY, EXPENSE_CATEGORIES } from "../constants/expenseCategories";
import {
  createExpenseAllocationsBatch,
  createAndSubmitExpense,
  createExpenseDraft,
  linkExpenseAttachments,
  listExpenses,
  submitExpense,
  uploadAttachment,
  uploadAttachments,
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

type RecordState = "missing_material" | "ready" | "submitted";
type TableSection = { key: "active" | "submitted"; records: Expense[] };

const month = currentReimbursementMonth();
const expenses = ref<Expense[]>([]);
const loading = ref(false);
const saving = ref(false);
const error = ref("");
const success = ref("");
const isComposerOpen = ref(true);
const targetExpenseId = ref<number | null>(null);
const isNewSubstitute = ref(false);
const evidenceAttachments = ref<Attachment[]>([]);
const stagedInvoice = ref<Attachment | null>(null);
const evidenceInput = ref<HTMLInputElement | null>(null);
const invoiceInput = ref<HTMLInputElement | null>(null);
const evidenceDragging = ref(false);
const invoiceDragging = ref(false);

const expenseForm = ref<{ project_name: string; actual_amount: string; category: string }>({
  project_name: "",
  actual_amount: "",
  category: DEFAULT_EXPENSE_CATEGORY,
});

const currentMonthExpenses = computed(() => expenses.value.filter((expense) => expense.expense_month === month));
const submittedRecords = computed(() => currentMonthExpenses.value.filter((expense) => expense.status !== "pending"));
const submittedTotal = computed(() => submittedRecords.value.reduce((sum, record) => sum + Number(record.actual_amount), 0));
const materialMissingCount = computed(() => currentMonthExpenses.value.filter((record) => record.status === "pending" && (!record.allocation_count || !record.attachments.length)).length);
const tableSections = computed<TableSection[]>(() => {
  const active = currentMonthExpenses.value.filter((record) => record.status === "pending");
  const submitted = currentMonthExpenses.value.filter((record) => record.status !== "pending");
  return [
    ...(active.length ? [{ key: "active" as const, records: active }] : []),
    ...(submitted.length ? [{ key: "submitted" as const, records: submitted }] : []),
  ];
});
const targetExpense = computed(() => expenses.value.find((expense) => expense.id === targetExpenseId.value) ?? null);
const isEditingExisting = computed(() => targetExpenseId.value !== null);
const selectedInvoiceItem = computed(() => {
  const items = stagedInvoice.value?.ocr_result.invoice_items;
  if (!Array.isArray(items)) return null;
  return items.find((item) => item && typeof item === "object" && typeof (item as Record<string, unknown>).amount === "number") as Record<string, unknown> | null;
});
const selectedInvoiceAmount = computed(() => Number(selectedInvoiceItem.value?.amount) || 0);
const canSubmitNew = computed(() => Boolean(stagedInvoice.value && selectedInvoiceItem.value && Number(expenseForm.value.actual_amount) > 0 && selectedInvoiceAmount.value >= Number(expenseForm.value.actual_amount)));
const canSubmitExisting = computed(() => Boolean(targetExpense.value && targetExpense.value.allocation_count > 0 && targetExpense.value.remaining_amount <= 0));

function recordState(expense: Expense): RecordState {
  if (expense.status === "pending" && (expense.allocation_count === 0 || expense.remaining_amount > 0)) return "missing_material";
  if (expense.status === "pending") return "ready";
  return "submitted";
}

function recordStateLabel(expense: Expense): string {
  const state = recordState(expense);
  if (state === "missing_material") return "待补材料";
  if (state === "ready") return "待提交";
  return "已提交";
}

function recordStateClass(expense: Expense): string {
  const state = recordState(expense);
  if (state === "missing_material") return "bg-amber-100 text-amber-800";
  if (state === "ready") return "bg-teal-50 text-teal-800";
  return "bg-slate-100 text-slate-600";
}

function resetComposer() {
  targetExpenseId.value = null;
  evidenceAttachments.value = [];
  stagedInvoice.value = null;
  isNewSubstitute.value = false;
  expenseForm.value = { project_name: "", actual_amount: "", category: DEFAULT_EXPENSE_CATEGORY };
}

function startNewExpense() {
  resetComposer();
  isComposerOpen.value = true;
  error.value = "";
  success.value = "";
}

function openExistingExpense(expense: Expense) {
  targetExpenseId.value = expense.id;
  isComposerOpen.value = true;
  isNewSubstitute.value = expense.is_substitute;
  expenseForm.value = {
    project_name: expense.project_name,
    actual_amount: String(expense.actual_amount),
    category: expense.category,
  };
  evidenceAttachments.value = [];
  stagedInvoice.value = null;
  error.value = "";
  success.value = "";
  window.scrollTo({ top: 0, behavior: "smooth" });
}

async function load() {
  loading.value = true;
  error.value = "";
  try {
    expenses.value = await listExpenses();
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

function invoiceIndexAndItem(attachment: Attachment): { index: number; item: Record<string, unknown> } | null {
  const items = invoiceItemsOf(attachment);
  const index = items.findIndex((item) => typeof item.amount === "number" && Number(item.amount) > 0);
  return index >= 0 ? { index, item: items[index] } : null;
}

type PreparedInvoiceLink = {
  index: number;
  item: Record<string, unknown>;
  note: string;
  buyerConfirmed: boolean;
};

function prepareInvoiceLink(attachment: Attachment, actualAmount: number): PreparedInvoiceLink {
  const invoice = invoiceIndexAndItem(attachment);
  if (!invoice) throw new Error("发票未识别到有效金额，请重新上传");
  const amount = Number(invoice.item.amount);
  if (amount < actualAmount) throw new Error("发票金额不足，请补充金额更足的发票");
  const note = amount === actualAmount ? "" : window.prompt("票面金额高于报销金额，请填写替票说明：", "替票")?.trim() ?? "";
  if (amount > actualAmount && !note) throw new Error("需要填写替票说明");
  const buyerConfirmed = isBuyerConfirmationNeeded(invoice.item)
    ? window.confirm("发票购买方需要人工确认，确认继续吗？")
    : false;
  if (isBuyerConfirmationNeeded(invoice.item) && !buyerConfirmed) throw new Error("已取消提交，请确认发票购买方");
  return { ...invoice, note, buyerConfirmed };
}

async function linkInvoiceToExpense(expenseId: number, attachment: Attachment, actualAmount: number, prepared = prepareInvoiceLink(attachment, actualAmount)): Promise<Expense> {
  return createExpenseAllocationsBatch({
    expense_id: expenseId,
    invoices: [{ attachment_id: attachment.id, invoice_item_index: prepared.index }],
    note: prepared.note,
    buyer_confirmed: prepared.buyerConfirmed,
  });
}

async function handleEvidenceFiles(files: File[]) {
  if (!files.length) return;
  saving.value = true;
  error.value = "";
  try {
    const uploaded = await uploadAttachments(files);
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
  if (files.length > 1) {
    error.value = "发票一次只能上传 1 张";
    return;
  }
  saving.value = true;
  error.value = "";
  try {
    const uploaded = await uploadAttachment(files[0]);
    if (targetExpenseId.value) {
      await linkInvoiceToExpense(targetExpenseId.value, uploaded, Number(expenseForm.value.actual_amount));
      await load();
      success.value = "发票已上传并关联";
    } else {
      stagedInvoice.value = uploaded;
      success.value = "发票已上传并完成识别";
    }
  } catch (err) {
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
  const prepared = stagedInvoice.value ? prepareInvoiceLink(stagedInvoice.value, actualAmount) : null;
  if (submitAfter) {
    if (!stagedInvoice.value || !prepared) throw new Error("请先上传发票");
    return createAndSubmitExpense({
      ...payload,
      invoices: [{ attachment_id: stagedInvoice.value.id, invoice_item_index: prepared.index }],
      attachment_ids: evidenceAttachments.value.map((item) => item.id),
      note: prepared.note,
      buyer_confirmed: prepared.buyerConfirmed,
    });
  }

  let created = await createExpenseDraft(payload);
  if (evidenceAttachments.value.length) {
    created = await linkExpenseAttachments(created.id, { attachment_ids: evidenceAttachments.value.map((item) => item.id) });
  }
  if (stagedInvoice.value) {
    created = await linkInvoiceToExpense(created.id, stagedInvoice.value, actualAmount, prepared ?? undefined);
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
      await submitExpense(current.id);
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

function stagedInvoiceText(key: string[]): string {
  return selectedInvoiceItem.value ? invoiceText(selectedInvoiceItem.value, key) : "待识别";
}

onMounted(load);
watch(() => props.refreshKey, load);
</script>

<template>
  <div class="mx-auto max-w-6xl space-y-7">
    <header class="flex flex-wrap items-end justify-between gap-5 border-b border-slate-200 pb-5">
      <div class="flex flex-wrap items-end gap-x-7 gap-y-4">
        <div>
          <p class="text-xs font-semibold uppercase tracking-[0.16em] text-teal-700">JetBao / {{ month }}</p>
          <h1 class="mt-2 text-3xl font-semibold tracking-tight text-ink">本月报销</h1>
        </div>
        <div class="flex items-end gap-6 border-l border-slate-200 pl-7">
          <div><p class="text-xs text-slate-500">已提交</p><p class="mt-1 text-sm font-semibold text-ink">{{ formatCurrency(submittedTotal) }} <span class="font-medium text-slate-500">/ {{ submittedRecords.length }} 笔</span></p></div>
          <div><p class="text-xs text-slate-500">待补材料</p><p class="mt-1 text-sm font-semibold text-amber-700">{{ materialMissingCount }} 笔</p></div>
        </div>
      </div>
      <button class="primary-button" type="button" @click="isComposerOpen ? (isComposerOpen = false) : startNewExpense()">
        <X v-if="isComposerOpen" class="h-4 w-4" /><Plus v-else class="h-4 w-4" />
        {{ isComposerOpen ? "收起" : "新建报销" }}
      </button>
    </header>

    <p v-if="error" class="border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">{{ error }}</p>
    <p v-if="success" class="border border-teal-200 bg-teal-50 px-4 py-3 text-sm text-teal-800">{{ success }}</p>

    <section v-if="isComposerOpen" class="border-y border-slate-200 bg-white">
      <div class="p-5">
        <div class="grid gap-x-7 gap-y-5 lg:grid-cols-[minmax(0,1fr)_150px_190px_150px]">
          <label class="block"><span class="block text-[11px] font-semibold tracking-[0.08em] text-slate-400">报销事项</span><input v-model="expenseForm.project_name" :disabled="isEditingExisting" class="mt-1 h-9 w-full border-0 border-b border-slate-300 bg-transparent p-0 text-[15px] font-medium text-ink outline-none transition focus:border-teal-700 disabled:text-slate-500" placeholder="填写报销事项" /></label>
          <label class="block"><span class="block text-[11px] font-semibold tracking-[0.08em] text-slate-400">金额</span><input v-model="expenseForm.actual_amount" :disabled="isEditingExisting" class="mt-1 h-9 w-full border-0 border-b border-slate-300 bg-transparent p-0 text-[15px] font-medium text-ink outline-none transition focus:border-teal-700 disabled:text-slate-500" inputmode="decimal" placeholder="0.00" /></label>
          <label class="block"><span class="block text-[11px] font-semibold tracking-[0.08em] text-slate-400">类别</span><select v-model="expenseForm.category" :disabled="isEditingExisting" class="mt-1 h-9 w-full border-0 border-b border-slate-300 bg-transparent p-0 text-[15px] font-medium text-ink outline-none transition focus:border-teal-700 disabled:text-slate-500"><option v-for="category in EXPENSE_CATEGORIES" :key="category">{{ category }}</option></select></label>
          <div><span class="block text-[11px] font-semibold tracking-[0.08em] text-slate-400">替票</span><div class="mt-1 flex h-9 items-center gap-4 border-b border-slate-300 text-[14px] font-medium"><button class="h-full border-b-2 px-1 transition" :class="!isNewSubstitute ? 'border-slate-800 text-ink' : 'border-transparent text-slate-400 hover:text-slate-700'" :disabled="isEditingExisting" type="button" @click="isNewSubstitute = false">否</button><button class="h-full border-b-2 px-1 transition" :class="isNewSubstitute ? 'border-orange-500 text-orange-700' : 'border-transparent text-slate-400 hover:text-slate-700'" :disabled="isEditingExisting" type="button" @click="isNewSubstitute = true">是</button></div></div>
        </div>
      </div>

      <input ref="evidenceInput" class="hidden" type="file" accept="image/*,.pdf" multiple @change="handleEvidenceInput" />
      <input ref="invoiceInput" class="hidden" type="file" accept="image/*,.pdf" @change="handleInvoiceInput" />
      <div class="grid gap-px border-y border-slate-200 bg-slate-200 lg:grid-cols-2">
        <div class="space-y-3 bg-white p-5">
          <div class="flex items-center justify-between"><span class="field-label">上传佐证材料</span><span class="text-xs text-slate-500">可一次上传多张</span></div>
          <button class="flex min-h-28 w-full flex-col items-center justify-center border border-dashed px-4 text-center transition" :class="evidenceDragging ? 'border-teal-600 bg-teal-50' : 'border-slate-300 bg-slate-50 hover:border-teal-600 hover:bg-teal-50'" :disabled="saving" type="button" @click="evidenceInput?.click()" @dragenter.prevent="evidenceDragging = true" @dragover.prevent="evidenceDragging = true" @dragleave.prevent="evidenceDragging = false" @drop.prevent="handleEvidenceDrop"><Loader2 v-if="saving" class="h-5 w-5 animate-spin text-teal-700" /><ImagePlus v-else class="h-5 w-5 text-teal-700" /><span class="mt-2 text-sm font-medium text-slate-800">{{ evidenceDragging ? "松开上传" : "点击或拖拽上传佐证材料（可多选）" }}</span></button>
          <div v-if="evidenceAttachments.length || targetExpense?.attachments.length" class="space-y-1 border-l-2 border-slate-400 bg-slate-50 px-3 py-2 text-xs text-slate-600"><div v-for="attachment in [...(targetExpense?.attachments ?? []), ...evidenceAttachments]" :key="attachment.id" class="flex items-center gap-2"><ImagePlus class="h-3.5 w-3.5 text-slate-500" /><span class="truncate">{{ attachment.original_filename }}</span></div></div>
        </div>

        <div class="space-y-3 bg-white p-5">
          <div class="flex items-center justify-between"><span class="field-label">上传发票</span><span class="text-xs text-slate-500">一次上传 1 张</span></div>
          <button class="flex min-h-28 w-full flex-col items-center justify-center border border-dashed px-4 text-center transition" :class="invoiceDragging ? 'border-teal-600 bg-teal-50' : 'border-slate-300 bg-slate-50 hover:border-teal-600 hover:bg-teal-50'" :disabled="saving || Boolean(stagedInvoice)" type="button" @click="invoiceInput?.click()" @dragenter.prevent="invoiceDragging = true" @dragover.prevent="invoiceDragging = true" @dragleave.prevent="invoiceDragging = false" @drop.prevent="handleInvoiceDrop"><Loader2 v-if="saving" class="h-5 w-5 animate-spin text-teal-700" /><FilePlus2 v-else class="h-5 w-5 text-teal-700" /><span class="mt-2 text-sm font-medium text-slate-800">{{ invoiceDragging ? "松开上传" : stagedInvoice ? "已上传 1 张发票" : "点击或拖拽上传 1 张发票" }}</span></button>
          <div v-if="stagedInvoice && selectedInvoiceItem" class="grid grid-cols-2 gap-x-4 gap-y-2 border-l-2 border-teal-600 bg-slate-50 px-3 py-3 text-xs text-slate-500"><span>金额</span><strong class="text-right text-slate-900">{{ formatCurrency(Number(selectedInvoiceItem.amount)) }}</strong><span>项目名称</span><strong class="truncate text-right text-slate-900">{{ stagedInvoiceText(["item_name", "goods_name", "title", "sub_type_description"]) }}</strong><span>销售方</span><strong class="truncate text-right text-slate-900">{{ stagedInvoiceText(["seller", "seller_name"]) }}</strong><span>票种</span><strong class="truncate text-right text-slate-900">{{ stagedInvoiceText(["sub_type_description", "type_description"]) }}</strong></div>
          <div v-else-if="targetExpense?.allocation_count" class="border-l-2 border-teal-600 bg-slate-50 px-3 py-3 text-xs text-teal-700">发票已关联</div>
        </div>
      </div>

      <div class="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 px-5 py-4"><p class="text-xs text-slate-500">{{ isEditingExisting ? "补齐发票后即可提交这笔报销。" : "没有发票也可以先保存，记录会显示为待补材料。" }}</p><div class="flex gap-2"><button v-if="!isEditingExisting" class="secondary-button h-9 px-3 text-xs" :disabled="saving" type="button" @click="saveDraft">保存待补</button><button v-else class="secondary-button h-9 px-3 text-xs" type="button" @click="isComposerOpen = false">关闭</button><button class="primary-button h-9 px-3 text-xs" :disabled="saving || (isEditingExisting ? !canSubmitExisting : !canSubmitNew)" type="button" @click="submitCurrent"><Loader2 v-if="saving" class="h-3.5 w-3.5 animate-spin" /><CheckCircle2 v-else class="h-3.5 w-3.5" /> 提交报销</button></div></div>
    </section>

    <section>
      <div class="mb-3 flex items-center justify-between"><h2 class="section-title">本月记录</h2><span class="text-xs text-slate-500">{{ currentMonthExpenses.length }} 笔</span></div>
      <div v-if="loading" class="border-y border-slate-200 bg-white px-4 py-10 text-center text-sm text-slate-500">加载中...</div>
      <div v-else-if="!currentMonthExpenses.length" class="border-y border-slate-200 bg-white px-4 py-12 text-center text-sm text-slate-500">本月还没有报销记录，先新建一笔。</div>
      <div v-else class="overflow-x-auto border-y border-slate-200 bg-white">
        <table class="min-w-[900px] w-full text-left text-[13px]"><thead class="border-b border-slate-200 bg-slate-50 text-xs font-medium text-slate-500"><tr><th class="px-4 py-2.5">状态</th><th class="px-4 py-2.5">报销事项</th><th class="px-4 py-2.5">类别</th><th class="px-4 py-2.5 text-right">金额</th><th class="px-4 py-2.5">替票</th><th class="px-4 py-2.5">佐证</th><th class="px-4 py-2.5">发票</th><th class="px-4 py-2.5 text-right">操作</th></tr></thead><tbody v-for="section in tableSections" :key="section.key" class="divide-y divide-slate-100" :class="section.key === 'submitted' ? 'border-t-4 border-slate-300' : ''"><tr v-for="record in section.records" :key="record.id" class="h-14 transition hover:bg-slate-50"><td class="px-4 py-2"><span class="status-pill" :class="recordStateClass(record)">{{ recordStateLabel(record) }}</span></td><td class="px-4 py-2 font-medium text-ink">{{ record.project_name || record.category }}</td><td class="px-4 py-2 text-slate-600">{{ record.category }}</td><td class="px-4 py-2 text-right font-medium text-ink">{{ formatCurrency(record.actual_amount) }}</td><td class="px-4 py-2"><span :class="record.is_substitute ? 'text-orange-700' : 'text-slate-500'">{{ record.is_substitute ? "是" : "否" }}</span></td><td class="px-4 py-2"><span :class="record.attachments.length ? 'text-slate-700' : 'text-amber-700'">{{ record.attachments.length ? `${record.attachments.length} 份` : "未上传" }}</span></td><td class="px-4 py-2"><span :class="record.allocation_count ? 'text-teal-700' : 'text-amber-700'">{{ record.allocation_count ? "已上传" : "未上传" }}</span></td><td class="px-4 py-2 text-right"><button v-if="recordState(record) === 'missing_material'" class="secondary-button h-8 px-2.5 text-xs" type="button" @click="openExistingExpense(record)">补材料</button><button v-else-if="recordState(record) === 'ready'" class="primary-button h-8 px-2.5 text-xs" :disabled="saving" type="button" @click="submitRecord(record)">提交报销</button><button v-else-if="record.status === 'matched'" class="secondary-button h-8 px-2.5 text-xs" :disabled="saving" type="button" @click="withdraw(record)">撤回</button><span v-else class="text-xs text-slate-400">已完成</span></td></tr></tbody></table>
      </div>
    </section>
  </div>
</template>
