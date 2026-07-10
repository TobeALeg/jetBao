<script setup lang="ts">
import { computed, ref } from "vue";
import { CheckCircle2, FilePlus2, ImagePlus, Plus, X } from "lucide-vue-next";
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
const activeRecords = computed(() => records.value.filter((record) => record.state !== "submitted"));
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

function completeMaterials(record: MonthRecord) {
  record.evidenceCount = 2;
  record.invoices = [
    { amount: record.amount, projectName: record.projectName, seller: "已识别销售方", type: "电子普通发票" },
  ];
  record.state = "ready";
}

function submitRecord(record: MonthRecord) {
  record.state = "submitted";
}

function withdrawRecord(record: MonthRecord) {
  record.state = "ready";
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
        <div class="grid gap-3 sm:grid-cols-[minmax(0,1fr)_140px_140px_120px]">
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
          <label class="block">
            <span class="field-label">替票</span>
            <select class="field-input mt-1"><option>否</option><option>是</option></select>
          </label>
        </div>
      </div>

      <div class="grid gap-px border-y border-slate-200 bg-slate-200 lg:grid-cols-2">
        <div class="space-y-3 bg-white p-5">
          <div class="flex items-center justify-between"><span class="field-label">上传佐证材料</span><span class="text-xs text-slate-500">可一次上传多张</span></div>
          <button class="flex min-h-28 w-full flex-col items-center justify-center border border-dashed border-slate-300 bg-slate-50 px-4 text-center transition hover:border-teal-600 hover:bg-teal-50" type="button" @click="hasNewEvidence = true">
            <ImagePlus class="h-5 w-5 text-teal-700" />
            <span class="mt-2 text-sm font-medium text-slate-800">点击或拖拽上传佐证材料（可多选）</span>
          </button>
          <div v-if="hasNewEvidence" class="space-y-2 border-l-2 border-slate-400 bg-slate-50 px-3 py-3 text-xs text-slate-600">
            <div class="flex items-center gap-3"><ImagePlus class="h-4 w-4 text-slate-500" /><span class="font-medium text-slate-800">滴滴行程单.png</span></div>
            <div class="flex items-center gap-3"><ImagePlus class="h-4 w-4 text-slate-500" /><span class="font-medium text-slate-800">支付截图.png</span></div>
          </div>
        </div>

        <div class="space-y-3 bg-white p-5">
          <div class="flex items-center justify-between"><span class="field-label">上传发票</span><span class="text-xs text-slate-500">一次上传 1 张</span></div>
          <button class="flex min-h-28 w-full flex-col items-center justify-center border border-dashed border-slate-300 bg-slate-50 px-4 text-center transition hover:border-teal-600 hover:bg-teal-50" type="button" @click="hasNewInvoice = true">
            <FilePlus2 class="h-5 w-5 text-teal-700" />
            <span class="mt-2 text-sm font-medium text-slate-800">点击或拖拽上传 1 张发票</span>
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
      <div class="overflow-x-auto border-y border-slate-200 bg-white">
        <table class="min-w-[900px] w-full text-left text-[13px]">
          <thead class="border-b border-slate-200 bg-slate-50 text-xs font-medium text-slate-500">
            <tr>
              <th class="px-4 py-2.5">状态</th>
              <th class="px-4 py-2.5">报销事项</th>
              <th class="px-4 py-2.5">类别</th>
              <th class="px-4 py-2.5 text-right">金额</th>
              <th class="px-4 py-2.5">替票</th>
              <th class="px-4 py-2.5">佐证</th>
              <th class="px-4 py-2.5">发票</th>
              <th class="px-4 py-2.5 text-right">操作</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100">
            <tr v-for="record in activeRecords" :key="record.id" class="h-14 transition hover:bg-slate-50">
              <td class="px-4 py-2"><span class="status-pill" :class="recordStateClass(record.state)">{{ recordStateLabel(record.state) }}</span></td>
              <td class="px-4 py-2 font-medium text-ink">{{ record.projectName }}</td>
              <td class="px-4 py-2 text-slate-600">{{ record.category }}</td>
              <td class="px-4 py-2 text-right font-medium text-ink">{{ formatCurrency(record.amount) }}</td>
              <td class="px-4 py-2"><span :class="record.substitute ? 'text-orange-700' : 'text-slate-500'">{{ record.substitute ? '是' : '否' }}</span></td>
              <td class="px-4 py-2"><span :class="record.evidenceCount ? 'text-slate-700' : 'text-amber-700'">{{ record.evidenceCount ? `${record.evidenceCount} 份` : '未上传' }}</span></td>
              <td class="px-4 py-2"><span :class="record.invoices.length ? 'text-teal-700' : 'text-amber-700'">{{ record.invoices.length ? '已上传' : '未上传' }}</span></td>
              <td class="px-4 py-2 text-right">
                <button v-if="record.state === 'missing_material'" class="secondary-button h-8 px-2.5 text-xs" type="button" @click="completeMaterials(record)">补材料</button>
                <button v-else-if="record.state === 'ready'" class="primary-button h-8 px-2.5 text-xs" type="button" @click="submitRecord(record)">提交报销</button>
                <button v-else class="secondary-button h-8 px-2.5 text-xs" type="button" @click="withdrawRecord(record)">撤回</button>
              </td>
            </tr>
          </tbody>
          <tbody v-if="submittedRecords.length" class="divide-y divide-slate-100 border-t-4 border-slate-300">
            <tr v-for="record in submittedRecords" :key="record.id" class="h-14 bg-slate-50/40 transition hover:bg-slate-50">
              <td class="px-4 py-2"><span class="status-pill" :class="recordStateClass(record.state)">{{ recordStateLabel(record.state) }}</span></td>
              <td class="px-4 py-2 font-medium text-ink">{{ record.projectName }}</td>
              <td class="px-4 py-2 text-slate-600">{{ record.category }}</td>
              <td class="px-4 py-2 text-right font-medium text-ink">{{ formatCurrency(record.amount) }}</td>
              <td class="px-4 py-2"><span :class="record.substitute ? 'text-orange-700' : 'text-slate-500'">{{ record.substitute ? '是' : '否' }}</span></td>
              <td class="px-4 py-2"><span :class="record.evidenceCount ? 'text-slate-700' : 'text-amber-700'">{{ record.evidenceCount ? `${record.evidenceCount} 份` : '未上传' }}</span></td>
              <td class="px-4 py-2"><span :class="record.invoices.length ? 'text-teal-700' : 'text-amber-700'">{{ record.invoices.length ? '已上传' : '未上传' }}</span></td>
              <td class="px-4 py-2 text-right"><button class="secondary-button h-8 px-2.5 text-xs" type="button" @click="withdrawRecord(record)">撤回</button></td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>
