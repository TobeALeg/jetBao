<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { ArrowRight, CheckCircle2, FileText, PlusCircle, Sparkles } from "lucide-vue-next";
import ExpenseTable from "../components/ExpenseTable.vue";
import QuickDraftForm from "../components/QuickDraftForm.vue";
import StatStrip from "../components/StatStrip.vue";
import { createExpenseDraft, listExpenses } from "../services/api";
import { currentMonth, formatCurrency } from "../utils/format";
import type { DraftExpenseCreatePayload, Expense, User } from "../types";

type StatTone = "default" | "warning" | "danger";
type StatItem = {
  label: string;
  value: string;
  tone?: StatTone;
};

const props = defineProps<{
  user: User;
  refreshKey: number;
}>();

const emit = defineEmits<{
  "complete-draft": [expense: Expense];
}>();

const expenses = ref<Expense[]>([]);
const loading = ref(true);
const error = ref("");
const success = ref("");
const showDraftForm = ref(false);
const savingDraft = ref(false);

const thisMonth = currentMonth();

const monthlyTotal = computed(() =>
  expenses.value
    .filter((item) => item.expense_month === thisMonth && item.status === "submitted")
    .reduce((sum, item) => sum + Number(item.actual_amount), 0)
);

const draftCount = computed(() => expenses.value.filter((item) => item.status === "draft").length);

const pendingOcrCount = computed(() =>
  expenses.value.reduce((sum, item) => {
    return sum + item.attachments.filter((file) => file.ocr_status !== "success").length;
  }, 0)
);

const duplicateCount = computed(() => expenses.value.filter((item) => item.has_duplicate).length);

const stats = computed<StatItem[]>(() => [
  { label: "本月已提交", value: formatCurrency(monthlyTotal.value) },
  { label: "待补材料", value: String(draftCount.value), tone: draftCount.value ? "warning" : "default" },
  { label: "待确认 OCR", value: String(pendingOcrCount.value), tone: pendingOcrCount.value ? "warning" : "default" },
  { label: "疑似重复", value: String(duplicateCount.value), tone: duplicateCount.value ? "danger" : "default" }
]);

type BannerKind = "empty" | "has-drafts" | "has-ocr" | "all-clear";
const bannerKind = computed<BannerKind>(() => {
  if (!expenses.value.length) return "empty";
  if (draftCount.value > 0) return "has-drafts";
  if (pendingOcrCount.value > 0) return "has-ocr";
  return "all-clear";
});

async function load() {
  loading.value = true;
  error.value = "";
  try {
    expenses.value = await listExpenses();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "加载失败";
  } finally {
    loading.value = false;
  }
}

async function submitDraft(payload: DraftExpenseCreatePayload) {
  savingDraft.value = true;
  error.value = "";
  success.value = "";
  try {
    await createExpenseDraft(payload);
    showDraftForm.value = false;
    await load();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "保存失败";
  } finally {
    savingDraft.value = false;
  }
}

function handleAttachmentUploaded(updated: Expense) {
  expenses.value = expenses.value.map((item) => (item.id === updated.id ? updated : item));
  error.value = "";
  success.value = "附件已保存";
}

function handleUploadError(message: string) {
  success.value = "";
  error.value = message;
}

onMounted(load);
watch(() => props.refreshKey, load);
</script>

<template>
  <div class="mx-auto max-w-7xl space-y-5">
    <div class="flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
      <div>
        <h1 class="page-title">我的报销</h1>
        <p class="muted mt-1">{{ user.employee_name }}，{{ thisMonth }} 的报销概览。</p>
      </div>
      <button class="primary-button" type="button" @click="showDraftForm = true">
        <PlusCircle class="h-4 w-4" />
        记一笔
      </button>
    </div>

    <div v-if="bannerKind === 'empty'" class="action-banner-info">
      <Sparkles class="mt-0.5 h-5 w-5 shrink-0 text-teal-600" />
      <div class="flex-1">
        <div class="font-medium">开始使用 JetBao</div>
        <div class="mt-0.5 text-teal-800">先点「记一笔」录入一笔报销，然后上传发票进行匹配。</div>
      </div>
      <button class="primary-button h-9 shrink-0" type="button" @click="showDraftForm = true">
        记第一笔
        <ArrowRight class="h-4 w-4" />
      </button>
    </div>
    <div v-else-if="bannerKind === 'has-drafts'" class="action-banner-warn">
      <FileText class="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />
      <div class="flex-1">
        <div class="font-medium">有 {{ draftCount }} 笔草稿待补材料</div>
        <div class="mt-0.5 text-amber-800">草稿需要上传发票并完成匹配后才能提交。去工作台补全材料吧。</div>
      </div>
      <button class="primary-button h-9 shrink-0" type="button" @click="emit('complete-draft', expenses.find(e => e.status === 'draft')!)">
        去补材料
        <ArrowRight class="h-4 w-4" />
      </button>
    </div>
    <div v-else-if="bannerKind === 'has-ocr'" class="action-banner-warn">
      <FileText class="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />
      <div class="flex-1">
        <div class="font-medium">有 {{ pendingOcrCount }} 个附件待确认 OCR</div>
        <div class="mt-0.5 text-amber-800">发票识别结果需要人工确认，请到工作台检查。</div>
      </div>
    </div>
    <div v-else class="action-banner-success">
      <CheckCircle2 class="mt-0.5 h-5 w-5 shrink-0 text-teal-600" />
      <div class="flex-1">
        <div class="font-medium">本月报销已全部提交</div>
        <div class="mt-0.5 text-teal-700">没有待处理的项目。如有新的报销需求，随时记一笔。</div>
      </div>
    </div>

    <QuickDraftForm v-if="showDraftForm" :saving="savingDraft" @submit="submitDraft" @cancel="showDraftForm = false" />
    <StatStrip :stats="stats" />
    <p v-if="success" class="rounded-md bg-teal-50 px-3 py-2 text-sm text-teal-800">{{ success }}</p>
    <p v-if="error" class="rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-700">{{ error }}</p>
    <ExpenseTable
      :expenses="expenses"
      :loading="loading"
      @complete-draft="emit('complete-draft', $event)"
      @attachment-uploaded="handleAttachmentUploaded"
      @upload-error="handleUploadError"
    />
  </div>
</template>
