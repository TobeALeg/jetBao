<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { CheckCheck, ChevronRight, Download, Eye, Search } from "lucide-vue-next";
import AdminExpenseReviewModal from "../components/AdminExpenseReviewModal.vue";
import {
  approveExpense,
  approveAllExpenses,
  downloadExportPackage,
  listLedger,
  listOwnLedger,
  listUsers,
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
  employee_id: "",
  status: "",
});

const rows = ref<LedgerRow[]>([]);
const employeeOptions = ref<Array<{ id: number; name: string }>>([]);
const loading = ref(false);
const error = ref("");
const success = ref("");

const reviewRow = ref<LedgerRow | null>(null);
const reviewOpen = ref(false);
const exporting = ref(false);
const approvingAll = ref(false);
const latestSearchId = ref(0);
const appliedQueryParams = ref<Record<string, string> | null>(null);

const expandedMonths = ref(new Set<string>());
const currentMonth = new Date().toISOString().slice(0, 7);
const FIRST_EXPENSE_YEAR = 2026;

const yearOptions = computed(() => {
  const currentYear = Math.max(new Date().getFullYear(), FIRST_EXPENSE_YEAR);
  return Array.from(
    { length: currentYear - FIRST_EXPENSE_YEAR + 1 },
    (_, index) => String(currentYear - index)
  );
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

function queryKey(params: Record<string, string>): string {
  return JSON.stringify(Object.entries(params).sort(([left], [right]) => left.localeCompare(right)));
}

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
const reviewableCount = computed(() => rows.value.filter((row) => row.status === "matched").length);
const resultsAreCurrent = computed(
  () => appliedQueryParams.value !== null && queryKey(appliedQueryParams.value) === queryKey(ledgerQueryParams.value)
);

async function search() {
  const searchId = ++latestSearchId.value;
  const querySnapshot = { ...ledgerQueryParams.value };
  loading.value = true;
  error.value = "";
  success.value = "";
  try {
    const result = isAdmin.value
      ? await listLedger(querySnapshot)
      : await listOwnLedger(querySnapshot);
    if (searchId !== latestSearchId.value) return;
    rows.value = result;
    appliedQueryParams.value = querySnapshot;
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
    if (searchId !== latestSearchId.value) return;
    error.value = err instanceof Error ? err.message : "加载失败";
  } finally {
    if (searchId === latestSearchId.value) loading.value = false;
  }
}

async function loadEmployeeNames() {
  if (!isAdmin.value) return;
  try {
    const users = await listUsers();
    employeeOptions.value = users
      .filter((user) => user.is_active)
      .map((user) => ({
        id: user.id,
        name: user.employee_name.trim() || user.email || user.username,
      }))
      .sort((left, right) => left.name.localeCompare(right.name, "zh-CN"));
  } catch (err) {
    error.value = err instanceof Error ? err.message : "加载员工列表失败";
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

// 硬规则：action(青) 只表示"需要你动手"；等审核/已归档降为 neutral / done
function statusClass(status: string, rejectReason = ""): string {
  if (status === "pending" && rejectReason) return "state-danger";
  if (status === "matched") return "state-neutral";
  if (status === "reviewed") return "state-done";
  return "state-warn";
}

// 左侧 3px 色条：不依赖颜色的第二个状态信号（色盲 / 强光下仍可读）
function statusBarClass(status: string, rejectReason = ""): string {
  if (status === "pending" && rejectReason) return "border-l-rose-600";
  if (status === "reviewed") return "border-l-slate-300";
  if (status === "matched") return "border-l-slate-300";
  return "border-l-amber-600";
}

function employeeRowClass(row: LedgerRow): string {
  if (row.status === "reviewed") return "bg-state-done-soft text-slate-500";
  if (row.status === "pending" && row.reject_reason) return "bg-state-danger-soft/40";
  return "";
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

async function handleApproveAll() {
  if (approvingAll.value || !reviewableCount.value || !resultsAreCurrent.value || !appliedQueryParams.value) return;
  const querySnapshot = { ...appliedQueryParams.value };
  if (!window.confirm(`确认通过当前筛选结果中的 ${reviewableCount.value} 笔待审核报销？`)) return;
  approvingAll.value = true;
  error.value = "";
  success.value = "";
  try {
    const result = await approveAllExpenses(querySnapshot);
    await search();
    emit("expensesChanged");
    success.value = result.approved_count
      ? `已通过 ${result.approved_count} 笔报销`
      : "没有仍处于待审核状态的报销";
  } catch (err) {
    error.value = err instanceof Error ? err.message : "批量审核失败";
  } finally {
    approvingAll.value = false;
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
    await downloadExportPackage(params);
    success.value = "导出成功：包含四页 Excel 与按公司/人员/报销类别整理的发票压缩包";
  } catch (err) {
    error.value = err instanceof Error ? err.message : "导出失败";
  } finally {
    exporting.value = false;
  }
}

onMounted(async () => {
  await search();
  await loadEmployeeNames();
});
watch(() => props.refreshKey, search);
watch([filterYear, filterMonthPart, () => filters.value.company_entity, () => filters.value.employee_id, () => filters.value.status], search);
</script>

<template>
  <div class="page">
    <div class="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 class="page-title">{{ isAdmin ? "报销记录总览" : "我的报销记录" }}</h1>
        <p class="muted mt-1">{{ isAdmin ? "所有人的报销记录，可按年份、月份筛选并归档查看。" : "查看你的历史报销记录。" }}</p>
      </div>
      <div v-if="isAdmin" class="flex flex-wrap items-center gap-2">
        <!-- 本屏唯一的实心主操作 -->
        <button
          class="primary-button is-anchor shrink-0"
          :disabled="approvingAll || loading || !resultsAreCurrent || !reviewableCount"
          type="button"
          @click="handleApproveAll"
        >
          <CheckCheck class="h-4 w-4" />
          {{ approvingAll ? "通过中..." : `一键通过（${reviewableCount}）` }}
        </button>
        <button
          class="secondary-button shrink-0"
          :disabled="exporting"
          type="button"
          @click="handleExport"
        >
          <Download class="h-4 w-4" /> {{ exporting ? "导出中..." : "导出" }}
        </button>
      </div>
    </div>

    <!-- Filters -->
    <section class="tool-panel p-4 sm:p-5">
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
          <select v-model="filters.employee_id" class="field-input mt-1 w-full">
            <option value="">全部</option>
            <option v-for="option in employeeOptions" :key="option.id" :value="String(option.id)">
              {{ option.name }}
            </option>
          </select>
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
          <button class="primary-button w-full" type="button" @click="search">
            <Search class="h-4 w-4" /> 查询
          </button>
        </div>
      </div>
    </section>

    <p v-if="error" class="rounded-control bg-state-danger-soft px-3 py-2 text-sm text-state-danger-ink">{{ error }}</p>
    <p v-if="success" class="rounded-control bg-state-action-soft px-3 py-2 text-sm text-state-action-ink">{{ success }}</p>

    <div v-if="loading" class="py-12 text-center text-sm text-slate-500">加载中...</div>

    <div v-else-if="!rows.length" class="empty-state">
      <div class="empty-state-icon">
        <Search class="h-6 w-6" />
      </div>
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
          class="tool-panel overflow-hidden"
        >
          <button
            class="flex w-full items-center justify-between px-5 py-4 text-left transition duration-1 ease-standard hover:bg-surface-soft"
            type="button"
            :aria-expanded="expandedMonths.has(month)"
            @click="toggleMonth(month)"
          >
            <div class="flex min-w-0 items-center gap-3">
              <!-- 单个箭头：向右 → 向下，旋转而非换图标，这样过渡才连得上 -->
              <ChevronRight
                class="h-4 w-4 shrink-0 text-slate-400 transition-transform duration-2 ease-standard"
                :class="expandedMonths.has(month) ? 'rotate-90' : ''"
              />
              <h2 class="truncate text-base font-semibold text-slate-900">{{ formatMonthLabel(month) }}</h2>
              <span class="shrink-0 text-xs text-slate-500">{{ group.length }} 笔</span>
            </div>
            <span class="num shrink-0 pl-3 text-sm font-semibold text-slate-700">{{ formatCurrency(groupTotal(group)) }}</span>
          </button>

          <!-- 展开过渡：grid-template-rows 0fr↔1fr，无需测量内容高度即可动画（与手风琴组件同一套做法） -->
          <Transition name="collapse">
            <div v-if="expandedMonths.has(month)" class="collapse-grid">
              <div class="collapse-clip">
                <div class="overflow-x-auto border-t border-hairline">
                  <table class="w-full min-w-[72rem] table-fixed divide-y divide-hairline text-left text-sm">
                    <colgroup>
                      <col v-if="isAdmin" class="w-[7rem]" />
                      <col class="w-[10rem]" />
                      <col class="w-[7rem]" />
                      <col class="w-[6.5rem]" />
                      <col />
                      <col class="w-[4.5rem]" />
                      <col class="w-[5.5rem]" />
                      <col class="w-[8rem]" />
                      <col v-if="isAdmin" class="w-[13.5rem]" />
                    </colgroup>
                    <thead class="bg-surface-soft text-xs font-medium text-slate-500">
                      <tr>
                        <th v-if="isAdmin" class="px-4 py-3">员工</th>
                        <th class="px-4 py-3">项目</th>
                        <th class="px-4 py-3">类别</th>
                        <th class="px-4 py-3">金额</th>
                        <th class="px-4 py-3">发票</th>
                        <th class="px-4 py-3">替票</th>
                        <th class="px-4 py-3">状态</th>
                        <th class="px-4 py-3">时间</th>
                        <th v-if="isAdmin" class="px-4 py-3">操作</th>
                      </tr>
                    </thead>
                    <tbody class="divide-y divide-hairline bg-white">
                      <tr
                        v-for="row in group"
                        :key="row.id"
                        class="transition duration-2 ease-standard"
                        :class="isAdmin ? (row.status === 'reviewed' ? 'bg-state-done-soft text-slate-500' : 'hover:bg-surface-soft') : employeeRowClass(row)"
                      >
                        <td v-if="isAdmin" class="truncate whitespace-nowrap px-4 py-3 font-medium" :class="row.status === 'reviewed' ? '' : 'text-slate-900'" :title="row.employee_name">
                          {{ row.employee_name }}
                        </td>
                        <td class="truncate px-4 py-3 font-medium" :class="row.status === 'reviewed' ? '' : 'text-slate-900'" :title="row.project_name || row.note || ''">
                          {{ row.project_name || row.note || "-" }}
                        </td>
                        <td class="truncate whitespace-nowrap px-4 py-3 text-slate-600">{{ row.category }}</td>
                        <td class="num whitespace-nowrap px-4 py-3 font-medium" :class="row.status === 'reviewed' ? '' : 'text-slate-900'">{{ formatCurrency(row.actual_amount) }}</td>
                        <td class="px-4 py-3 text-slate-600">
                          <div v-if="row.allocation_summary" class="truncate text-xs" :title="row.allocation_summary">{{ row.allocation_summary }}</div>
                          <span v-else>-</span>
                        </td>
                        <td class="px-4 py-3">
                          <span class="chip">{{ row.is_substitute ? "是" : "否" }}</span>
                        </td>
                        <td class="border-l-[3px] px-4 py-3" :class="statusBarClass(row.status, row.reject_reason)">
                          <span class="status-pill" :class="statusClass(row.status, row.reject_reason)">
                            {{ statusLabel(row.status, row.reject_reason, isAdmin) }}
                          </span>
                          <div v-if="row.reject_reason" class="mt-1 truncate text-xs text-state-danger-ink" :title="row.reject_reason">打回：{{ row.reject_reason }}</div>
                        </td>
                        <td class="whitespace-nowrap px-4 py-3 text-slate-500">{{ formatDate(row.created_at) }}</td>
                        <td v-if="isAdmin" class="whitespace-nowrap px-4 py-3">
                          <div class="flex flex-nowrap items-center gap-1.5">
                            <!-- 管理员的「通过」是本屏最该点的动作，用柔和主色；
                                 打回用危险色；其余为次级/幽灵，避免满屏实心块 -->
                            <button
                              v-if="row.status === 'matched' || row.status === 'reviewed'"
                              class="secondary-button btn-xs"
                              type="button"
                              @click="openReview(row)"
                            >
                              <Eye class="h-3.5 w-3.5 shrink-0" />
                              <span>预览</span>
                            </button>
                            <button
                              v-if="row.status === 'matched'"
                              class="primary-button btn-xs"
                              type="button"
                              @click="handleApprove(row)"
                            >
                              通过
                            </button>
                            <button
                              v-if="row.status === 'matched'"
                              class="secondary-button btn-xs text-state-warn-ink hover:border-state-warn-line hover:bg-state-warn-soft"
                              type="button"
                              @click="handleReject(row)"
                            >
                              打回
                            </button>
                            <button
                              v-if="row.status === 'reviewed'"
                              class="secondary-button btn-xs"
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
              </div>
            </div>
          </Transition>
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

<style scoped>
/* 「从上到下抽出」：动画 grid-template-rows 0fr↔1fr，
   不需要测量内容高度，因此任意行数都能平滑展开。
   与 components/InlineAccordionSelect.vue 用同一套做法，保持一致。 */
.collapse-grid {
  display: grid;
  grid-template-rows: 1fr;
}

.collapse-clip {
  min-height: 0;
  overflow: hidden;
}

.collapse-enter-active,
.collapse-leave-active {
  transition: grid-template-rows var(--dur-3) var(--ease-standard);
}

.collapse-enter-from,
.collapse-leave-to {
  grid-template-rows: 0fr;
}

@media (prefers-reduced-motion: reduce) {
  .collapse-enter-active,
  .collapse-leave-active {
    transition: none !important;
  }
}
</style>
