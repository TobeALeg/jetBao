<script setup lang="ts">
import { computed, ref } from "vue";
import { CheckCircle2, FilePlus2, ImagePlus, Plus, ReceiptText, X } from "lucide-vue-next";
import { currentReimbursementMonth, formatCurrency } from "../utils/format";
import type { User } from "../types";

defineProps<{
  user: User;
  refreshKey: number;
}>();

defineEmits<{
  refreshed: [];
}>();

type RecordState = "missing_material" | "ready" | "submitted";

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
const isComposerOpen = ref(true);
const hasNewInvoice = ref(true);
const hasNewEvidence = ref(true);

// 静态布局：下一步再把这组展示模型接回 expenses / attachments API。
const records = ref<MonthRecord[]>([
  {
    id: 1,
    projectName: "客户拜访交通",
    category: "差旅交通",
    amount: 86,
    state: "missing_material",
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

const submittedRecords = computed(() => records.value.filter((record) => record.state === "submitted"));
const submittedTotal = computed(() => submittedRecords.value.reduce((sum, record) => sum + record.amount, 0));
const materialMissingCount = computed(() => records.value.filter((record) => record.state === "missing_material" || record.evidenceCount === 0).length);

function recordStateLabel(state: RecordState) {
  if (state === "missing_material") return "待补材料";
  if (state === "ready") return "待提交";
  return "已提交";
}

function recordStateClass(state: RecordState) {
  if (state === "missing_material") return "bg-amber-100 text-amber-800";
  if (state === "ready") return "bg-teal-50 text-teal-800";
  return "bg-slate-100 text-slate-600";
}
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
          <div>
            <p class="text-xs text-slate-500">已提交</p>
            <p class="mt-1 text-sm font-semibold text-ink">{{ formatCurrency(submittedTotal) }} <span class="font-medium text-slate-500">/ {{ submittedRecords.length }} 笔</span></p>
          </div>
          <div>
            <p class="text-xs text-slate-500">待补材料</p>
            <p class="mt-1 text-sm font-semibold text-amber-700">{{ materialMissingCount }} 笔</p>
          </div>
        </div>
      </div>
      <button class="primary-button" type="button" @click="isComposerOpen = !isComposerOpen">
        <X v-if="isComposerOpen" class="h-4 w-4" />
        <Plus v-else class="h-4 w-4" />
        {{ isComposerOpen ? "收起" : "新建报销" }}
      </button>
    </header>

    <section v-if="isComposerOpen" class="border-y border-slate-200 bg-white">
      <div class="p-5">
        <div class="grid gap-3 sm:grid-cols-[minmax(0,1fr)_160px_160px]">
          <label class="block">
            <span class="field-label">报销事项</span>
            <input class="field-input mt-1" value="客户拜访打车" />
          </label>
          <label class="block">
            <span class="field-label">金额</span>
            <input class="field-input mt-1" inputmode="decimal" value="86.00" />
          </label>
          <label class="block">
            <span class="field-label">类别</span>
            <select class="field-input mt-1"><option>差旅交通</option><option>办公用品</option><option>市场活动</option></select>
          </label>
        </div>
      </div>

      <div class="grid gap-px border-y border-slate-200 bg-slate-200 lg:grid-cols-2">
        <div class="space-y-3 bg-white p-5">
          <div class="flex items-center justify-between"><span class="field-label">上传佐证材料</span><span class="text-xs text-slate-500">付款或订单截图</span></div>
          <button class="flex min-h-28 w-full flex-col items-center justify-center border border-dashed border-slate-300 bg-slate-50 px-4 text-center transition hover:border-teal-600 hover:bg-teal-50" type="button" @click="hasNewEvidence = true">
            <ImagePlus class="h-5 w-5 text-teal-700" />
            <span class="mt-2 text-sm font-medium text-slate-800">点击或拖拽上传佐证材料</span>
          </button>
          <div v-if="hasNewEvidence" class="flex items-center gap-3 border-l-2 border-slate-400 bg-slate-50 px-3 py-3 text-xs text-slate-600">
            <ImagePlus class="h-4 w-4 text-slate-500" />
            <span class="font-medium text-slate-800">滴滴行程单.png</span>
          </div>
        </div>

        <div class="space-y-3 bg-white p-5">
          <div class="flex items-center justify-between"><span class="field-label">上传发票</span><span class="text-xs text-slate-500">上传后自动识别</span></div>
          <button class="flex min-h-28 w-full flex-col items-center justify-center border border-dashed border-slate-300 bg-slate-50 px-4 text-center transition hover:border-teal-600 hover:bg-teal-50" type="button" @click="hasNewInvoice = true">
            <FilePlus2 class="h-5 w-5 text-teal-700" />
            <span class="mt-2 text-sm font-medium text-slate-800">点击或拖拽上传发票</span>
          </button>
          <div v-if="hasNewInvoice" class="grid grid-cols-2 gap-x-4 gap-y-2 border-l-2 border-teal-600 bg-slate-50 px-3 py-3 text-xs text-slate-500">
              <span>金额</span><strong class="text-right text-slate-900">¥86.00</strong>
              <span>项目名称</span><strong class="text-right text-slate-900">出租车费</strong>
              <span>销售方</span><strong class="text-right text-slate-900">上海大众出租汽车有限公司</strong>
              <span>票种</span><strong class="text-right text-slate-900">出租车电子发票</strong>
            </div>
          </div>
        </div>

      <div class="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 px-5 py-4">
        <p class="text-xs text-slate-500">没有发票也可以保存，记录会显示为“待补材料”。</p>
        <div class="flex gap-2">
          <button class="secondary-button h-9 px-3 text-xs" type="button">保存待补</button>
          <button class="primary-button h-9 px-3 text-xs" type="button" :disabled="!hasNewInvoice"><CheckCircle2 class="h-3.5 w-3.5" /> 提交报销</button>
        </div>
      </div>
    </section>

    <section>
      <div class="mb-3 flex items-center justify-between">
        <h2 class="section-title">本月记录</h2>
        <span class="text-xs text-slate-500">{{ records.length }} 笔</span>
      </div>
      <div class="divide-y divide-slate-200 border-y border-slate-200 bg-white">
        <article v-for="record in records" :key="record.id" class="px-5 py-5">
          <div class="flex flex-wrap items-start justify-between gap-4">
            <div class="min-w-0">
              <div class="flex flex-wrap items-center gap-2">
                <span class="status-pill" :class="recordStateClass(record.state)">{{ recordStateLabel(record.state) }}</span>
                <span v-if="record.substitute" class="status-pill bg-orange-100 text-orange-800">替票</span>
                <span v-if="record.evidenceCount === 0" class="status-pill bg-amber-50 text-amber-800">缺佐证</span>
                <span class="text-xs text-slate-500">{{ record.category }}</span>
              </div>
              <p class="mt-2 font-semibold text-ink">{{ record.projectName }}</p>
              <p class="mt-1 text-sm text-slate-500">佐证材料 {{ record.evidenceCount }} 份</p>
            </div>
            <div class="flex items-center gap-3"><strong class="text-base text-ink">{{ formatCurrency(record.amount) }}</strong><button v-if="record.state !== 'submitted'" class="secondary-button h-9 px-3 text-xs" type="button" @click="isComposerOpen = true"><ReceiptText class="h-3.5 w-3.5" /> 补充材料</button></div>
          </div>

          <div v-if="record.invoices.length" class="mt-4 grid gap-2 sm:grid-cols-2">
            <div v-for="invoice in record.invoices" :key="`${invoice.seller}-${invoice.projectName}`" class="grid grid-cols-2 gap-x-4 gap-y-2 border-l-2 px-3 py-3 text-xs text-slate-500" :class="record.substitute ? 'border-orange-500 bg-orange-50/60' : 'border-teal-600 bg-slate-50'">
              <span>金额</span><strong class="text-right text-slate-900">{{ formatCurrency(invoice.amount) }}</strong>
              <span>项目名称</span><strong class="text-right text-slate-900">{{ invoice.projectName }}</strong>
              <span>销售方</span><strong class="text-right text-slate-900">{{ invoice.seller }}</strong>
              <span>票种</span><strong class="text-right text-slate-900">{{ invoice.type }}</strong>
            </div>
          </div>
        </article>
      </div>
    </section>
  </div>
</template>
