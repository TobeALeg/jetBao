<script setup lang="ts">
import { onMounted, ref } from "vue";
import LedgerFilters from "../components/LedgerFilters.vue";
import { listLedger } from "../services/api";
import { currentMonth, formatCurrency, formatDate } from "../utils/format";
import type { LedgerRow } from "../types";

const filters = ref<Record<string, string>>({
  month: currentMonth(),
  company_entity: "",
  employee: "",
  category: "",
  is_substitute: "",
  has_duplicate: ""
});

const rows = ref<LedgerRow[]>([]);
const loading = ref(false);
const error = ref("");

async function search() {
  loading.value = true;
  error.value = "";
  try {
    rows.value = await listLedger(filters.value);
  } catch (err) {
    error.value = err instanceof Error ? err.message : "加载台账失败";
  } finally {
    loading.value = false;
  }
}

onMounted(search);
</script>

<template>
  <div class="mx-auto max-w-7xl space-y-5">
    <div>
      <h1 class="page-title">管理后台</h1>
      <p class="muted mt-1">以台账为核心筛选报销记录。</p>
    </div>

    <LedgerFilters v-model="filters" @search="search" />
    <p v-if="error" class="rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-700">{{ error }}</p>

    <section class="tool-panel overflow-hidden rounded-lg">
      <div class="flex items-center justify-between border-b border-slate-200 px-5 py-4">
        <div>
          <h2 class="section-title">报销台账</h2>
          <p class="muted mt-1">{{ loading ? "正在加载..." : `共 ${rows.length} 笔` }}</p>
        </div>
      </div>

      <div v-if="loading" class="px-5 py-12 text-center text-sm text-slate-500">正在加载...</div>
      <div v-else-if="!rows.length" class="px-5 py-12 text-center text-sm text-slate-500">没有匹配记录</div>

      <div v-else class="overflow-x-auto">
        <table class="min-w-full divide-y divide-slate-200 text-left text-sm">
          <thead class="bg-slate-50 text-xs font-medium uppercase tracking-normal text-slate-500">
            <tr>
              <th class="px-5 py-3">公司主体</th>
              <th class="px-5 py-3">员工</th>
              <th class="px-5 py-3">月份</th>
              <th class="px-5 py-3">类别</th>
              <th class="px-5 py-3">实际金额</th>
              <th class="px-5 py-3">发票金额</th>
              <th class="px-5 py-3">替票</th>
              <th class="px-5 py-3">重复</th>
              <th class="px-5 py-3">附件</th>
              <th class="px-5 py-3">提交时间</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100 bg-white">
            <tr v-for="row in rows" :key="row.id" class="hover:bg-slate-50/70">
              <td class="min-w-56 px-5 py-4 text-slate-700">{{ row.company_entity }}</td>
              <td class="whitespace-nowrap px-5 py-4 font-medium text-slate-900">{{ row.employee_name }}</td>
              <td class="whitespace-nowrap px-5 py-4 text-slate-700">{{ row.expense_month }}</td>
              <td class="whitespace-nowrap px-5 py-4 text-slate-700">{{ row.category }}</td>
              <td class="whitespace-nowrap px-5 py-4 font-medium text-slate-900">{{ formatCurrency(row.actual_amount) }}</td>
              <td class="whitespace-nowrap px-5 py-4 text-slate-700">{{ formatCurrency(row.invoice_amount) }}</td>
              <td class="whitespace-nowrap px-5 py-4">
                <span class="status-pill" :class="row.is_substitute ? 'bg-amber-50 text-amber-700' : 'bg-slate-100 text-slate-600'">
                  {{ row.is_substitute ? "是" : "否" }}
                </span>
              </td>
              <td class="whitespace-nowrap px-5 py-4">
                <span class="status-pill" :class="row.has_duplicate ? 'bg-amber-50 text-amber-700' : 'bg-slate-100 text-slate-600'">
                  {{ row.has_duplicate ? "是" : "否" }}
                </span>
              </td>
              <td class="min-w-56 px-5 py-4 text-slate-600">{{ row.attachment_names || "-" }}</td>
              <td class="whitespace-nowrap px-5 py-4 text-slate-500">{{ formatDate(row.created_at) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>

