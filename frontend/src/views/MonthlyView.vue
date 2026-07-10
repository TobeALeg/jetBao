<script setup lang="ts">
import { computed, ref } from "vue";
import {
  AlertCircle,
  CheckCircle2,
  ChevronRight,
  FilePlus2,
  ImagePlus,
  Plus,
  ReceiptText,
  X,
} from "lucide-vue-next";
import { currentReimbursementMonth, formatCurrency } from "../utils/format";
import type { User } from "../types";

defineProps<{
  user: User;
  refreshKey: number;
}>();

defineEmits<{
  refreshed: [];
}>();

type RecordState = "missing_invoice" | "ready" | "submitted";

interface InvoiceSummary {
  amount: number;
  projectName: string;
  seller: string;
  type: string;
}

interface MonthRecord {
  id: number;
  projectName: string;
  category: string;
  amount: number;
  state: RecordState;
  evidenceCount: number;
  invoices: InvoiceSummary[];
  substitute?: boolean;
}

const month = currentReimbursementMonth();
const isComposerOpen = ref(false);
const selectedRecordId = ref(2);
const uploadTarget = ref<{ kind: "invoice" | "evidence"; recordId?: number } | null>(null);

// 静态布局：下一步再把这组展示模型接回 expenses / attachments API。
const records = ref<MonthRecord[]>([
  {
    id: 1,
    projectName: "客户拜访交通",
    category: "差旅交通",
    amount: 86,
    state: "missing_invoice",
    evidenceCount: 0,
    invoices: [],
  },
  {
    id: 2,
    projectName: "办公室用品",
    category: "办公用品",
    amount: 320,
    state: "ready",
    evidenceCount: 1,
    invoices: [
      { amount: 320, projectName: "办公耗材", seller: "上海文具用品有限公司", type: "电子普通发票" },
    ],
  },
  {
    id: 3,
    projectName: "展会物料",
    category: "市场活动",
    amount: 1200,
    state: "submitted",
    evidenceCount: 2,
    substitute: true,
    invoices: [
      { amount: 1300, projectName: "展会制作服务", seller: "上海光合广告有限公司", type: "增值税电子普通发票" },
    ],
  },
]);

const missingInvoiceRecords = computed(() => records.value.filter((record) => record.state === "missing_invoice"));
const readyRecords = computed(() => records.value.filter((record) => record.state === "ready"));
const submittedRecords = computed(() => records.value.filter((record) => record.state === "submitted"));
const evidenceMissingCount = computed(() => records.value.filter((record) => record.evidenceCount === 0).length);
const submittedTotal = computed(() => submittedRecords.value.reduce((sum, record) => sum + record.amount, 0));
const selectedRecord = computed(() => records.value.find((record) => record.id === selectedRecordId.value) ?? records.value[0]);
const selectedInvoiceTotal = computed(() => selectedRecord.value.invoices.reduce((sum, invoice) => sum + invoice.amount, 0));
const selectedIsSubstitute = computed(() => Boolean(selectedRecord.value.substitute || (selectedInvoiceTotal.value && selectedInvoiceTotal.value !== selectedRecord.value.amount)));

function selectRecord(record: MonthRecord) {
  selectedRecordId.value = record.id;
}

function openUpload(kind: "invoice" | "evidence", record?: MonthRecord) {
  if (record) selectRecord(record);
  uploadTarget.value = { kind, recordId: record?.id };
}

function recordStateLabel(state: RecordState) {
  if (state === "missing_invoice") return "待补发票";
  if (state === "ready") return "待提交";
  return "已提交";
}

function recordStateClass(state: RecordState) {
  if (state === "missing_invoice") return "bg-amber-100 text-amber-800";
  if (state === "ready") return "bg-teal-50 text-teal-800";
  return "bg-slate-100 text-slate-600";
}
</script>

<template>
  <div class="mx-auto max-w-7xl space-y-7">
    <header class="flex flex-wrap items-end justify-between gap-5 border-b border-slate-200 pb-5">
      <div>
        <p class="text-xs font-semibold uppercase tracking-[0.16em] text-teal-700">JetBao / {{ month }}</p>
        <h1 class="mt-2 text-3xl font-semibold tracking-tight text-ink">本月报销</h1>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <button class="secondary-button" type="button" @click="openUpload('invoice')">
          <FilePlus2 class="h-4 w-4" /> 上传材料
        </button>
        <button class="primary-button" type="button" @click="isComposerOpen = !isComposerOpen">
          <X v-if="isComposerOpen" class="h-4 w-4" />
          <Plus v-else class="h-4 w-4" />
          {{ isComposerOpen ? "收起" : "记一笔" }}
        </button>
      </div>
    </header>

    <section v-if="isComposerOpen" class="border-y border-slate-200 bg-white py-5">
      <div class="grid gap-3 px-1 sm:grid-cols-[minmax(0,1.5fr)_160px_160px_auto] sm:items-end">
        <label class="block">
          <span class="field-label">报销事项</span>
          <input class="field-input mt-1" placeholder="如：客户拜访打车" />
        </label>
        <label class="block">
          <span class="field-label">金额</span>
          <input class="field-input mt-1" inputmode="decimal" placeholder="0.00" />
        </label>
        <label class="block">
          <span class="field-label">类别</span>
          <select class="field-input mt-1"><option>差旅交通</option><option>办公用品</option><option>市场活动</option></select>
        </label>
        <button class="primary-button" type="button">保存记录</button>
      </div>
    </section>

    <section class="grid gap-px overflow-hidden border border-slate-200 bg-slate-200 sm:grid-cols-3">
      <div class="bg-white px-5 py-4">
        <p class="text-xs text-slate-500">本月已提交</p>
        <p class="mt-1 text-xl font-semibold text-ink">{{ formatCurrency(submittedTotal) }}</p>
      </div>
      <div class="bg-white px-5 py-4">
        <p class="text-xs text-slate-500">待补发票</p>
        <p class="mt-1 text-xl font-semibold text-amber-700">{{ missingInvoiceRecords.length }} 笔</p>
      </div>
      <div class="bg-white px-5 py-4">
        <p class="text-xs text-slate-500">待补佐证</p>
        <p class="mt-1 text-xl font-semibold text-amber-700">{{ evidenceMissingCount }} 笔</p>
      </div>
    </section>

    <section v-if="missingInvoiceRecords.length || evidenceMissingCount" class="flex flex-wrap items-center justify-between gap-4 border border-amber-200 bg-amber-50 px-4 py-3">
      <div class="flex items-start gap-3 text-sm text-amber-950">
        <AlertCircle class="mt-0.5 h-4 w-4 shrink-0 text-amber-700" />
        <span>
          <strong>本月还有 {{ missingInvoiceRecords.length }} 笔待补发票</strong>
          <span v-if="evidenceMissingCount">，{{ evidenceMissingCount }} 笔尚未上传佐证材料。</span>
        </span>
      </div>
      <button class="text-sm font-medium text-amber-800 hover:text-amber-950" type="button" @click="openUpload('invoice')">现在上传 <ChevronRight class="inline h-4 w-4" /></button>
    </section>

    <section class="grid gap-7 xl:grid-cols-[minmax(0,1fr)_320px]">
      <div class="space-y-7">
        <div>
          <div class="mb-3 flex items-center justify-between">
            <h2 class="section-title">待补</h2>
            <span class="text-xs text-slate-500">还没有发票的报销记录</span>
          </div>
          <div class="divide-y divide-slate-200 border-y border-slate-200 bg-white">
            <article v-for="record in missingInvoiceRecords" :key="record.id" class="grid gap-4 px-5 py-5 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
              <button class="min-w-0 text-left" type="button" @click="selectRecord(record)">
                <div class="flex flex-wrap items-center gap-2">
                  <span class="status-pill" :class="recordStateClass(record.state)">{{ recordStateLabel(record.state) }}</span>
                  <span class="text-xs text-slate-500">{{ record.category }}</span>
                </div>
                <p class="mt-2 font-semibold text-ink">{{ record.projectName }}</p>
                <p class="mt-1 text-sm text-slate-500">尚未关联发票 · 佐证材料 {{ record.evidenceCount }} 份</p>
              </button>
              <div class="flex flex-wrap gap-2">
                <button class="secondary-button h-9 px-3 text-xs" type="button" @click="openUpload('invoice', record)"><ReceiptText class="h-3.5 w-3.5" /> 上传发票</button>
                <button class="secondary-button h-9 px-3 text-xs" type="button" @click="openUpload('evidence', record)"><ImagePlus class="h-3.5 w-3.5" /> 上传佐证</button>
                <strong class="flex items-center px-1 text-sm text-ink">{{ formatCurrency(record.amount) }}</strong>
              </div>
            </article>
          </div>
        </div>

        <div>
          <div class="mb-3 flex items-center justify-between">
            <h2 class="section-title">待提交</h2>
            <span class="text-xs text-slate-500">已选发票，确认试算后即可提交</span>
          </div>
          <div class="divide-y divide-slate-200 border-y border-slate-200 bg-white">
            <article v-for="record in readyRecords" :key="record.id" class="cursor-pointer px-5 py-5 transition hover:bg-slate-50" :class="selectedRecordId === record.id ? 'bg-teal-50/40' : ''" @click="selectRecord(record)">
              <div class="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <div class="flex items-center gap-2"><span class="status-pill" :class="recordStateClass(record.state)">{{ recordStateLabel(record.state) }}</span><span class="text-xs text-slate-500">{{ record.category }}</span></div>
                  <p class="mt-2 font-semibold text-ink">{{ record.projectName }}</p>
                </div>
                <div class="text-right"><strong class="text-base text-ink">{{ formatCurrency(record.amount) }}</strong><p class="mt-1 text-xs text-slate-500">佐证 {{ record.evidenceCount }} 份</p></div>
              </div>
              <div class="mt-4 grid gap-2 sm:grid-cols-2">
                <div v-for="invoice in record.invoices" :key="`${invoice.seller}-${invoice.projectName}`" class="grid grid-cols-2 gap-x-4 gap-y-2 border-l-2 border-teal-600 bg-slate-50 px-3 py-3 text-xs text-slate-500">
                  <span>金额</span><strong class="text-right text-slate-900">{{ formatCurrency(invoice.amount) }}</strong>
                  <span>项目名称</span><strong class="text-right text-slate-900">{{ invoice.projectName }}</strong>
                  <span>销售方</span><strong class="text-right text-slate-900">{{ invoice.seller }}</strong>
                  <span>票种</span><strong class="text-right text-slate-900">{{ invoice.type }}</strong>
                </div>
              </div>
              <button class="mt-4 inline-flex items-center gap-1 text-xs font-medium text-teal-700 hover:text-teal-900" type="button" @click.stop="openUpload('evidence', record)"><ImagePlus class="h-3.5 w-3.5" /> 上传佐证材料</button>
            </article>
          </div>
        </div>

        <div>
          <div class="mb-3 flex items-center justify-between"><h2 class="section-title">已提交</h2><span class="text-xs text-slate-500">本月正式报销记录</span></div>
          <div class="divide-y divide-slate-200 border-y border-slate-200 bg-white">
            <article v-for="record in submittedRecords" :key="record.id" class="cursor-pointer px-5 py-5 transition hover:bg-slate-50" :class="selectedRecordId === record.id ? 'bg-slate-50' : ''" @click="selectRecord(record)">
              <div class="flex flex-wrap items-start justify-between gap-4">
                <div><div class="flex items-center gap-2"><span class="status-pill" :class="recordStateClass(record.state)">{{ recordStateLabel(record.state) }}</span><span v-if="record.substitute" class="status-pill bg-orange-100 text-orange-800">替票</span></div><p class="mt-2 font-semibold text-ink">{{ record.projectName }}</p></div>
                <strong class="text-base text-ink">{{ formatCurrency(record.amount) }}</strong>
              </div>
            </article>
          </div>
        </div>
      </div>

      <aside class="h-fit border-t-2 border-teal-700 bg-white xl:sticky xl:top-6">
        <div class="border-b border-slate-200 px-5 py-4"><p class="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">报销试算</p><h2 class="mt-1 text-base font-semibold text-ink">{{ selectedRecord.projectName }}</h2></div>
        <div class="space-y-5 p-5">
          <div class="grid grid-cols-2 gap-px overflow-hidden border border-slate-200 bg-slate-200 text-sm"><div class="bg-white px-3 py-3"><span class="block text-xs text-slate-500">报销金额</span><strong class="mt-1 block text-ink">{{ formatCurrency(selectedRecord.amount) }}</strong></div><div class="bg-white px-3 py-3"><span class="block text-xs text-slate-500">发票合计</span><strong class="mt-1 block text-ink">{{ selectedInvoiceTotal ? formatCurrency(selectedInvoiceTotal) : "未上传" }}</strong></div></div>
          <div v-if="!selectedRecord.invoices.length" class="border border-dashed border-amber-300 bg-amber-50 px-4 py-4 text-sm text-amber-900"><strong>缺少发票</strong><p class="mt-1 text-xs leading-5">上传发票后，系统会在这里给出试算结果。</p><button class="mt-3 text-xs font-semibold text-amber-800" type="button" @click="openUpload('invoice', selectedRecord)">上传发票</button></div>
          <div v-else class="border-l-4 px-4 py-3" :class="selectedIsSubstitute ? 'border-orange-500 bg-orange-50' : 'border-teal-600 bg-teal-50'"><p class="text-xs font-medium" :class="selectedIsSubstitute ? 'text-orange-800' : 'text-teal-800'">试算结果</p><p class="mt-1 text-lg font-semibold" :class="selectedIsSubstitute ? 'text-orange-900' : 'text-teal-900'">{{ selectedIsSubstitute ? '替票' : '实票' }}</p><p class="mt-1 text-xs leading-5" :class="selectedIsSubstitute ? 'text-orange-800' : 'text-teal-800'">{{ selectedIsSubstitute ? '票面金额与报销金额不一致，提交后会标记为替票。' : '票面金额与报销金额一致，可以提交。' }}</p></div>
          <button class="primary-button w-full" type="button" :disabled="!selectedRecord.invoices.length">提交报销</button>
        </div>
      </aside>
    </section>

    <div v-if="uploadTarget" class="fixed inset-0 z-30 grid place-items-center bg-slate-950/25 p-4" @click.self="uploadTarget = null">
      <section class="w-full max-w-md bg-white p-6 shadow-xl">
        <div class="flex items-start justify-between gap-4"><div><p class="text-xs font-semibold uppercase tracking-[0.14em] text-teal-700">上传材料</p><h2 class="mt-1 text-lg font-semibold text-ink">{{ uploadTarget.kind === 'invoice' ? '上传发票' : '上传佐证材料' }}</h2></div><button class="text-slate-400 hover:text-slate-700" type="button" @click="uploadTarget = null"><X class="h-5 w-5" /></button></div>
        <div class="mt-5 border border-dashed border-slate-300 bg-slate-50 px-5 py-10 text-center"><FilePlus2 class="mx-auto h-6 w-6 text-teal-700" /><p class="mt-3 text-sm font-medium text-slate-800">拖拽或点击选择文件</p><p class="mt-1 text-xs text-slate-500">{{ uploadTarget.kind === 'invoice' ? '发票会自动识别并进入试算。' : `将关联到「${selectedRecord.projectName}」。` }}</p></div>
      </section>
    </div>
  </div>
</template>
