<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ChevronDown, ChevronRight, Download, Search } from "lucide-vue-next";
import {
  approveExpense,
  downloadExport,
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

const filters = ref<Record<string, string>>({
  month: "",
  company_entity: "",
  employee: "",
  status: "",
});

const rows = ref<LedgerRow[]>([]);
const loading = ref(false);
const error = ref("");
const success = ref("");

const expandedMonths = ref(new Set<string>());
const currentMonth = new Date().toISOString().slice(0, 7);

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

const isAdmin = computed(() => props.user.role === "admin");

async function search() {
  loading.value = true;
  error.value = "";
  try {
    rows.value = await listLedger(filters.value);
    // Auto-expand current month
    if (filters.value.month) {
      expandedMonths.value = new Set([filters.value.month]);
    } else {
      expandedMonths.value = new Set(monthGroups.value.map(([m]) => m).filter((m) => m >= currentMonth));
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

function statusLabel(status: string): string {
  if (status === "pending") return "待处理";
  if (status === "matched") return "已提交";
  if (status === "reviewed") return "已完成";
  return status;
}

function statusClass(status: string): string {
  if (status === "matched") return "bg-teal-50 text-teal-700";
  if (status === "reviewed") return "bg-slate-100 text-slate-600";
  return "bg-amber-50 text-amber-700";
}

function groupTotal(group: LedgerRow[]): number {
  return group.reduce((sum, r) => sum + Number(r.actual_amount), 0);
}

async function handleApprove(row: LedgerRow) {
  if (!window.confirm(`确认审核通过「${row.employee_name} - ${row.project_name || '未命名'}」？`)) return;
  try {
    await approveExpense(row.id);
    await search();
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
    success.value = "已撤销审核";
  } catch (err) {
    error.value = err instanceof Error ? err.message : "操作失败";
  }
}

async function handleExportExcel() {
  try {
    await downloadExport(filters.value);
  } catch (err) {
    error.value = err instanceof Error ? err.message : "导出失败";
  }
}

async function handleExportPackage() {
  try {
    await downloadExportPackage(filters.value);
  } catch (err) {
    error.value = err instanceof Error ? err.message : "导出失败";
  }
}

onMounted(search);
</script>

<template>
  <div class="mx-auto max-w-7xl space-y-5">
    <div>
      <h1 class="page-title">所有记录</h1>
      <p class="muted mt-1">{{ isAdmin ? '所有人的报销记录，按月份归档。' : '你的所有报销记录。' }}</p>
    </div>

    <!-- Filters -->
    <section class="tool-panel overflow-hidden rounded-lg">
      <div class="flex flex-wrap items-end gap-3 p-5">
        <div>
          <label class="field-label">月份</label>
          <input v-model="filters.month" type="month" class="field-input mt-1" />
        </div>
        <div v-if="isAdmin">
          <label class="field-label">公司主体</label>
          <select v-model="filters.company_entity" class="field-input mt-1">
            <option value="">全部</option>
            <option>上海山途远智信息科技有限公司</option>
            <option>山途远智（上海）企业服务有限公司</option>
            <option>上海山途远智企业咨询有限公司</option>
          </select>
        </div>
        <div v-if="isAdmin">
          <label class="field-label">员工</label>
          <input v-model="filters.employee" class="field-input mt-1" placeholder="姓名" />
        </div>
        <div>
          <label class="field-label">状态</label>
          <select v-model="filters.status" class="field-input mt-1">
            <option value="">全部</option>
            <option value="pending">待处理</option>
            <option value="matched">已提交</option>
            <option value="reviewed">已完成</option>
          </select>
        </div>
        <button class="primary-button h-10" @click="search">
          <Search class="h-4 w-4" /> 查询
        </button>
        <div v-if="isAdmin" class="ml-auto flex gap-2">
          <button class="secondary-button h-10" @click="handleExportExcel">
            <Download class="h-4 w-4" /> 导出 Excel
          </button>
          <button class="secondary-button h-10" @click="handleExportPackage">
            <Download class="h-4 w-4" /> 导出明细包
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
      <section
        v-for="[month, group] in monthGroups"
        :key="month"
        class="tool-panel overflow-hidden rounded-lg"
      >
        <button
          class="flex w-full items-center justify-between px-5 py-4 text-left transition hover:bg-slate-50"
          @click="toggleMonth(month)"
        >
          <div class="flex items-center gap-3">
            <ChevronDown v-if="expandedMonths.has(month)" class="h-4 w-4 text-slate-400" />
            <ChevronRight v-else class="h-4 w-4 text-slate-400" />
            <h2 class="text-base font-semibold text-ink">{{ month }}</h2>
            <span class="text-xs text-slate-500">{{ group.length }} 笔</span>
          </div>
          <span class="text-sm font-semibold text-slate-700">{{ formatCurrency(groupTotal(group)) }}</span>
        </button>

        <div v-if="expandedMonths.has(month)" class="overflow-x-auto border-t border-slate-200">
          <table class="min-w-full divide-y divide-slate-200 text-left text-sm">
            <thead class="bg-slate-50 text-xs font-medium uppercase tracking-normal text-slate-500">
              <tr>
                <th v-if="isAdmin" class="px-5 py-3">员工</th>
                <th class="px-5 py-3">项目</th>
                <th class="px-5 py-3">类别</th>
                <th class="px-5 py-3">金额</th>
                <th class="px-5 py-3">发票</th>
                <th class="px-5 py-3">替票</th>
                <th class="px-5 py-3">状态</th>
                <th class="px-5 py-3">时间</th>
                <th class="px-5 py-3">操作</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100 bg-white">
              <tr v-for="row in group" :key="row.id" :class="row.status === 'reviewed' ? 'bg-slate-50/50 text-slate-500' : 'hover:bg-slate-50/70'">
                <td v-if="isAdmin" class="px-5 py-4 font-medium text-slate-900">{{ row.employee_name }}</td>
                <td class="min-w-32 px-5 py-4 font-medium text-slate-900">{{ row.project_name || row.note || "-" }}</td>
                <td class="px-5 py-4 text-slate-600">{{ row.category }}</td>
                <td class="px-5 py-4 font-medium text-slate-900">{{ formatCurrency(row.actual_amount) }}</td>
                <td class="px-5 py-4 text-slate-600">
                  <div v-if="row.allocation_summary" class="text-xs">{{ row.allocation_summary }}</div>
                  <span v-else>-</span>
                </td>
                <td class="px-5 py-4">
                  <span class="status-pill" :class="row.is_substitute ? 'bg-amber-50 text-amber-700' : 'bg-slate-100 text-slate-600'">
                    {{ row.is_substitute ? "是" : "否" }}
                  </span>
                </td>
                <td class="px-5 py-4">
                  <span class="status-pill" :class="statusClass(row.status)">{{ statusLabel(row.status) }}</span>
                  <div v-if="row.reject_reason" class="mt-1 text-xs text-rose-600">打回：{{ row.reject_reason }}</div>
                </td>
                <td class="px-5 py-4 text-slate-500">{{ formatDate(row.created_at) }}</td>
                <td class="px-5 py-4">
                  <div v-if="isAdmin" class="flex items-center gap-1.5">
                    <button
                      v-if="row.status === 'matched'"
                      class="h-7 rounded-md bg-teal-50 px-2 text-xs text-teal-700 transition hover:bg-teal-100"
                      @click="handleApprove(row)"
                    >
                      通过
                    </button>
                    <button
                      v-if="row.status === 'matched'"
                      class="h-7 rounded-md border border-amber-200 bg-amber-50 px-2 text-xs text-amber-700 transition hover:bg-amber-100"
                      @click="handleReject(row)"
                    >
                      打回
                    </button>
                    <button
                      v-if="row.status === 'reviewed'"
                      class="h-7 rounded-md border border-slate-200 px-2 text-xs text-slate-500 transition hover:bg-slate-100"
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
</template>
