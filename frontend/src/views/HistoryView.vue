<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { ChevronDown, ChevronRight, Download, Eye, Search } from "lucide-vue-next";
import AdminExpenseReviewModal from "../components/AdminExpenseReviewModal.vue";
import {
  approveExpense,
  downloadExportPackage,
  listLedger,
  rejectExpense,
  unreviewExpense,
} from "../services/api";
import { formatCurrency, formatDate } from "../utils/format";
import type { LedgerRow, User } from "../types";

const props = defineProps<{
  user: User;
  refreshKey: number;
}>();

const emit = defineEmits<{
  expensesChanged: [];
}>();

const filterYear = ref("");
const filterMonthPart = ref("");
const filters = ref<Record<string, string>>({
  company_entity: "",
  employee: "",
  status: "",
});

const rows = ref<LedgerRow[]>([]);
const loading = ref(false);
const error = ref("");
const success = ref("");

const reviewRow = ref<LedgerRow | null>(null);
const reviewOpen = ref(false);
const exporting = ref(false);

const expandedMonths = ref(new Set<string>());
const currentMonth = new Date().toISOString().slice(0, 7);

const yearOptions = computed(() => {
  const currentYear = new Date().getFullYear();
  return Array.from({ length: 8 }, (_, index) => String(currentYear - index));
});

const monthOptions = computed(() =>
  Array.from({ length: 12 }, (_, index) => {
    const value = String(index + 1).padStart(2, "0");
    return { value, label: `${index + 1} 月` };
  })
);

const ledgerQueryParams = computed(() => {
  const params: Record<string, string> = { ...filters.value };
  if (filterYear.value && filterMonthPart.value) {
    params.month = `${filterYear.value}-${filterMonthPart.value}`;
  } else if (filterYear.value) {
    params.year = filterYear.value;
  } else if (filterMonthPart.value) {
    params.month_part = filterMonthPart.value;
  }
  return params;
});

const exportPeriodLabel = computed(() => {
  if (filterYear.value && filterMonthPart.value) return `${filterYear.value}-${filterMonthPart.value}`;
  if (filterYear.value) return filterYear.value;
  if (filterMonthPart.value) return `第${Number(filterMonthPart.value)}月`;
  return "全部";
});

// Group by month
const monthGroups = computed(() => {
  const groups = new Map<string, LedgerRow[]>();
  for (const row of rows.value) {
    const month = row.expense_month;
    if (!groups.has(month)) groups.set(month, []);
    groups.get(month)!.push(row);
  }
  // Sort months descending
  return Array.from(groups.entries()).sort((a, b) => b[0].localeCompare(a[0]));
});

const yearGroups = computed(() => {
  const groups = new Map<string, Array<[string, LedgerRow[]]>>();
  for (const entry of monthGroups.value) {
    const year = entry[0].slice(0, 4);
    if (!groups.has(year)) groups.set(year, []);
    groups.get(year)!.push(entry);
  }
  return Array.from(groups.entries()).sort((a, b) => b[0].localeCompare(a[0]));
});

const showYearSections = computed(() => !filterYear.value && yearGroups.value.length > 1);

function formatMonthLabel(month: string): string {
  const [year, monthPart] = month.split("-");
  if (!year || !monthPart) return month;
  return `${year} 年 ${Number(monthPart)} 月`;
}

const isAdmin = computed(() => props.user.role === "admin");

async function search() {
  if (!isAdmin.value) return;
  loading.value = true;
  error.value = "";
  success.value = "";
  try {
    rows.value = await listLedger(ledgerQueryParams.value);
    const selectedMonth =
      filterYear.value && filterMonthPart.value ? `${filterYear.value}-${filterMonthPart.value}` : "";
    if (selectedMonth) {
      expandedMonths.value = new Set([selectedMonth]);
    } else if (filterYear.value) {
      expandedMonths.value = new Set(monthGroups.value.map(([month]) => month));
    } else {
      expandedMonths.value = new Set(monthGroups.value.map(([month]) => month).filter((month) => month >= currentMonth));
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : "加载失败";
  } finally {
    loading.value = false;
  }
}

function toggleMonth(month: string) {
  const next = new Set(expandedMonths.value);
  if (next.has(month)) next.delete(month);
  else next.add(month);
  expandedMonths.value = next;
}

function statusLabel(status: string, rejectReason = "", forAdmin = false): string {
  if (status === "pending" && rejectReason) return "已打回";
  if (status === "pending") return "待处理";
  if (status === "matched") return "已提交";
  if (status === "reviewed") return forAdmin ? "已完成" : "已完成";
  return status;
}

function statusClass(status: string, rejectReason = ""): string {
  if (status === "pending" && rejectReason) return "bg-rose-50 text-rose-700";
  if (status === "matched") return "bg-teal-50 text-teal-700";
  if (status === "reviewed") return "bg-slate-100 text-slate-500";
  return "bg-amber-50 text-amber-700";
}

function employeeRowClass(row: LedgerRow): string {
  if (row.status === "reviewed") return "bg-slate-50/80 text-slate-500";
  if (row.status === "pending" && row.reject_reason) return "bg-rose-50/30";
  return "hover:bg-slate-50/70";
}

function groupTotal(group: LedgerRow[]): number {
  return group.reduce((sum, r) => sum + Number(r.actual_amount), 0);
}

async function handleApprove(row: LedgerRow) {
  if (!window.confirm(`确认审核通过「${row.employee_name} - ${row.project_name || '未命名'}」？`)) return;
  try {
    await approveExpense(row.id);
    await search();
    emit("expensesChanged");
    success.value = "已审核通过";
  } catch (err) {
    error.value = err instanceof Error ? err.message : "操作失败";
  }
}

async function handleReject(row: LedgerRow) {
  const reason = window.prompt("打回原因（可选）：");
  if (reason === null) return;
  try {
    await rejectExpense(row.id, reason || undefined);
    await search();
    emit("expensesChanged");
    success.value = "已打回";
  } catch (err) {
    error.value = err instanceof Error ? err.message : "操作失败";
  }
}

async function handleUnreview(row: LedgerRow) {
  if (!window.confirm(`撤销审核「${row.employee_name} - ${row.project_name || '未命名'}」？`)) return;
  try {
    await unreviewExpense(row.id);
    await search();
    emit("expensesChanged");
    success.value = "已撤销审核";
  } catch (err) {
    error.value = err instanceof Error ? err.message : "操作失败";
  }
}

function openReview(row: LedgerRow) {
  reviewRow.value = row;
  reviewOpen.value = true;
}

function closeReview() {
  reviewOpen.value = false;
  reviewRow.value = null;
}

async function handleReviewApprove(row: LedgerRow) {
  closeReview();
  await handleApprove(row);
}

async function handleReviewReject(row: LedgerRow) {
  closeReview();
  await handleReject(row);
}

async function handleExport() {
  if (exporting.value) return;
  exporting.value = true;
  error.value = "";
  success.value = "";
  try {
    const params: Record<string, string> = {};
    if (filterYear.value && filterMonthPart.value) {
      params.month = `${filterYear.value}-${filterMonthPart.value}`;
    } else if (filterYear.value) {
      params.year = filterYear.value;
    } else if (filterMonthPart.value) {
      params.month_part = filterMonthPart.value;
    }
    if (filters.value.company_entity) {
      params.company_entity = filters.value.company_entity;
    }
    await downloadExportPackage(params, exportPeriodLabel.value);
    success.value = "导出成功：包含四页 Excel 与按板块/人员整理的发票压缩包";
  } catch (err) {
    error.value = err instanceof Error ? err.message : "导出失败";
  } finally {
    exporting.value = false;
  }
}

onMounted(search);
watch(() => props.refreshKey, search);
watch([filterYear, filterMonthPart, () => filters.value.company_entity, () => filters.value.employee, () => filters.value.status], search);
</script>

<template>
  <div class="mx-auto w-full max-w-[88rem] space-y-5">
    <div class="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 class="page-title">报销记录总览</h1>
        <p class="muted mt-1">{{ isAdmin ? "所有人的报销记录，可按年份、月份筛选并归档查看。" : "查看你的历史报销记录。" }}</p>
      </div>
      <button
        v-if="isAdmin"
        class="secondary-button h-10 shrink-0"
        :disabled="exporting"
        type="button"
        @click="handleExport"
      >
        <Download class="h-4 w-4" /> {{ exporting ? "导出中..." : "导出" }}
      </button>
    </div>

    <!-- Filters -->
    <section class="tool-panel rounded-lg p-4 sm:p-5">
      <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        <div>
          <label class="field-label">年份</label>
          <select v-model="filterYear" class="field-input mt-1 w-full">
            <option value="">全部</option>
            <option v-for="year in yearOptions" :key="year" :value="year">{{ year }} 年</option>
          </select>
        </div>
        <div>
          <label class="field-label">月份</label>
          <select v-model="filterMonthPart" class="field-input mt-1 w-full">
            <option value="">全部</option>
            <option v-for="option in monthOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
          </select>
        </div>
        <div v-if="isAdmin">
          <label class="field-label">公司主体</label>
          <select v-model="filters.company_entity" class="field-input mt-1 w-full">
            <option value="">全部</option>
            <option>上海山途远智信息科技有限公司</option>
            <option>山途远智（上海）企业服务有限公司</option>
            <option>上海山途远智企业咨询有限公司</option>
          </select>
        </div>
        <div v-if="isAdmin">
          <label class="field-label">员工</label>
          <input v-model="filters.employee" class="field-input mt-1 w-full" placeholder="姓名" />
        </div>
        <div>
          <label class="field-label">状态</label>
          <select v-model="filters.status" class="field-input mt-1 w-full">
            <option value="">全部</option>
            <option value="pending">待处理</option>
            <option value="matched">已提交</option>
            <option value="reviewed">已完成</option>
          </select>
        </div>
        <div class="flex items-end">
          <button class="primary-button h-10 w-full" type="button" @click="search">
            <Search class="h-4 w-4" /> 查询
          </button>
        </div>
      </div>
    </section>

    <p v-if="error" class="rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-700">{{ error }}</p>
    <p v-if="success" class="rounded-md bg-teal-50 px-3 py-2 text-sm text-teal-800">{{ success }}</p>

    <div v-if="loading" class="py-12 text-center text-sm text-slate-500">加载中...</div>

    <div v-else-if="!rows.length" class="empty-state py-12">
      <Search class="h-6 w-6" />
      <div>
        <div class="text-sm font-medium text-slate-700">没有匹配记录</div>
        <div class="mt-1 text-xs text-slate-500">调整筛选条件试试。</div>
      </div>
    </div>

    <!-- Month groups -->
    <div v-else class="space-y-4">
      <div v-for="[year, months] in yearGroups" :key="year" class="space-y-4">
        <div v-if="showYearSections" class="px-1 pt-2">
          <h2 class="text-sm font-semibold tracking-wide text-slate-500">{{ year }} 年</h2>
        </div>

        <section
          v-for="[month, group] in months"
          :key="month"
          class="tool-panel overflow-hidden rounded-lg"
        >
          <button
            class="flex w-full items-center justify-between px-5 py-4 text-left transition hover:bg-slate-50"
            type="button"
            @click="toggleMonth(month)"
          >
            <div class="flex min-w-0 items-center gap-3">
              <ChevronDown v-if="expandedMonths.has(month)" class="h-4 w-4 shrink-0 text-slate-400" />
              <ChevronRight v-else class="h-4 w-4 shrink-0 text-slate-400" />
              <h2 class="truncate text-base font-semibold text-ink">{{ formatMonthLabel(month) }}</h2>
              <span class="shrink-0 text-xs text-slate-500">{{ group.length }} 笔</span>
            </div>
            <span class="shrink-0 pl-3 text-sm font-semibold text-slate-700">{{ formatCurrency(groupTotal(group)) }}</span>
          </button>

          <div v-if="expandedMonths.has(month)" class="overflow-x-auto border-t border-slate-200">
            <table class="w-full min-w-[72rem] table-fixed divide-y divide-slate-200 text-left text-sm">
              <colgroup>
                <col v-if="isAdmin" class="w-[7rem]" />
                <col class="w-[10rem]" />
                <col class="w-[7rem]" />
                <col class="w-[6.5rem]" />
                <col />
                <col class="w-[4.5rem]" />
                <col class="w-[5.5rem]" />
                <col class="w-[8rem]" />
                <col class="w-[13.5rem]" />
              </colgroup>
              <thead class="bg-slate-50 text-xs font-medium text-slate-500">
                <tr>
                  <th v-if="isAdmin" class="px-4 py-3">员工</th>
                  <th class="px-4 py-3">项目</th>
                  <th class="px-4 py-3">类别</th>
                  <th class="px-4 py-3">金额</th>
                  <th class="px-4 py-3">发票</th>
                  <th class="px-4 py-3">替票</th>
                  <th class="px-4 py-3">状态</th>
                  <th class="px-4 py-3">时间</th>
                  <th class="px-4 py-3">操作</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-100 bg-white">
                <tr
                  v-for="row in group"
                  :key="row.id"
                  :class="isAdmin ? (row.status === 'reviewed' ? 'bg-slate-50/50 text-slate-500' : 'hover:bg-slate-50/70') : employeeRowClass(row)"
                >
                  <td v-if="isAdmin" class="truncate whitespace-nowrap px-4 py-3 font-medium text-slate-900" :title="row.employee_name">
                    {{ row.employee_name }}
                  </td>
                  <td class="truncate px-4 py-3 font-medium text-slate-900" :title="row.project_name || row.note || ''">
                    {{ row.project_name || row.note || "-" }}
                  </td>
                  <td class="truncate whitespace-nowrap px-4 py-3 text-slate-600">{{ row.category }}</td>
                  <td class="whitespace-nowrap px-4 py-3 font-medium text-slate-900">{{ formatCurrency(row.actual_amount) }}</td>
                  <td class="px-4 py-3 text-slate-600">
                    <div v-if="row.allocation_summary" class="truncate text-xs" :title="row.allocation_summary">{{ row.allocation_summary }}</div>
                    <span v-else>-</span>
                  </td>
                  <td class="px-4 py-3">
                    <span class="status-pill" :class="row.is_substitute ? 'bg-amber-50 text-amber-700' : 'bg-slate-100 text-slate-600'">
                      {{ row.is_substitute ? "是" : "否" }}
                    </span>
                  </td>
                  <td class="px-4 py-3">
                    <span class="status-pill whitespace-nowrap" :class="statusClass(row.status, row.reject_reason)">
                      {{ statusLabel(row.status, row.reject_reason, isAdmin) }}
                    </span>
                    <div v-if="row.reject_reason" class="mt-1 truncate text-xs text-rose-600" :title="row.reject_reason">打回：{{ row.reject_reason }}</div>
                  </td>
                  <td class="whitespace-nowrap px-4 py-3 text-slate-500">{{ formatDate(row.created_at) }}</td>
                  <td class="whitespace-nowrap px-4 py-3">
                    <div v-if="isAdmin" class="flex flex-nowrap items-center gap-1.5">
                      <button
                        v-if="row.status === 'matched' || row.status === 'reviewed'"
                        class="inline-flex h-7 shrink-0 items-center gap-1 whitespace-nowrap rounded-md border border-slate-200 px-2 text-xs text-slate-600 transition hover:bg-slate-100"
                        type="button"
                        @click="openReview(row)"
                      >
                        <Eye class="h-3.5 w-3.5 shrink-0" />
                        <span>预览</span>
                      </button>
                      <button
                        v-if="row.status === 'matched'"
                        class="inline-flex h-7 shrink-0 items-center whitespace-nowrap rounded-md bg-teal-50 px-2 text-xs text-teal-700 transition hover:bg-teal-100"
                        type="button"
                        @click="handleApprove(row)"
                      >
                        通过
                      </button>
                      <button
                        v-if="row.status === 'matched'"
                        class="inline-flex h-7 shrink-0 items-center whitespace-nowrap rounded-md border border-amber-200 bg-amber-50 px-2 text-xs text-amber-700 transition hover:bg-amber-100"
                        type="button"
                        @click="handleReject(row)"
                      >
                        打回
                      </button>
                      <button
                        v-if="row.status === 'reviewed'"
                        class="inline-flex h-7 shrink-0 items-center whitespace-nowrap rounded-md border border-slate-200 px-2 text-xs text-slate-500 transition hover:bg-slate-100"
                        type="button"
                        @click="handleUnreview(row)"
                      >
                        撤销
                      </button>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </div>

    <AdminExpenseReviewModal
      :open="reviewOpen"
      :row="reviewRow"
      @close="closeReview"
      @approve="handleReviewApprove"
      @reject="handleReviewReject"
    />
  </div>
</template>
