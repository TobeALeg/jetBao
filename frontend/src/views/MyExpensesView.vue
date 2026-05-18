<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import ExpenseTable from "../components/ExpenseTable.vue";
import StatStrip from "../components/StatStrip.vue";
import { listExpenses } from "../services/api";
import { currentMonth, formatCurrency } from "../utils/format";
import type { Expense, User } from "../types";

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

const expenses = ref<Expense[]>([]);
const loading = ref(true);
const error = ref("");

const thisMonth = currentMonth();

const monthlyTotal = computed(() =>
  expenses.value
    .filter((item) => item.expense_month === thisMonth)
    .reduce((sum, item) => sum + Number(item.actual_amount), 0)
);

const pendingOcrCount = computed(() =>
  expenses.value.reduce((sum, item) => {
    return sum + item.attachments.filter((file) => file.ocr_status !== "success").length;
  }, 0)
);

const duplicateCount = computed(() => expenses.value.filter((item) => item.has_duplicate).length);

const stats = computed<StatItem[]>(() => [
  { label: "本月报销总额", value: formatCurrency(monthlyTotal.value) },
  { label: "待确认 OCR", value: String(pendingOcrCount.value), tone: pendingOcrCount.value ? "warning" : "default" },
  { label: "疑似重复", value: String(duplicateCount.value), tone: duplicateCount.value ? "danger" : "default" }
]);

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
    </div>

    <StatStrip :stats="stats" />
    <p v-if="error" class="rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-700">{{ error }}</p>
    <ExpenseTable :expenses="expenses" :loading="loading" />
  </div>
</template>
