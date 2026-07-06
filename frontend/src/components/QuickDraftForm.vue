<script setup lang="ts">
import { reactive, ref } from "vue";
import { Save, X } from "lucide-vue-next";
import { DEFAULT_EXPENSE_CATEGORY, EXPENSE_CATEGORIES } from "../constants/expenseCategories";
import { currentReimbursementMonth } from "../utils/format";
import type { DraftExpenseCreatePayload } from "../types";

defineProps<{
  saving?: boolean;
}>();

const emit = defineEmits<{
  submit: [payload: DraftExpenseCreatePayload];
  cancel: [];
}>();

const form = reactive({
  project_name: "",
  actual_amount: "",
  expense_month: currentReimbursementMonth(),
  category: DEFAULT_EXPENSE_CATEGORY
});

const error = ref("");

function submit() {
  error.value = "";
  const amount = Number(form.actual_amount);
  if (!form.project_name.trim()) {
    error.value = "请填写项目名称。";
    return;
  }
  if (!amount || amount <= 0) {
    error.value = "请填写报销金额。";
    return;
  }

  emit("submit", {
    project_name: form.project_name.trim(),
    actual_amount: amount,
    expense_month: form.expense_month,
    category: form.category
  });
}
</script>

<template>
  <div class="fixed inset-0 z-40 grid place-items-center bg-slate-950/25 px-4 py-6">
    <section class="tool-panel w-full max-w-md rounded-lg p-5 shadow-xl">
      <div class="mb-4 flex items-center justify-between gap-3">
        <h2 class="section-title">记一笔</h2>
        <button class="secondary-button h-9 w-9 px-0" type="button" aria-label="关闭" @click="$emit('cancel')">
          <X class="h-4 w-4" />
        </button>
      </div>

      <form class="space-y-4" @submit.prevent="submit">
      <div>
        <label class="field-label" for="draft-project">项目名称</label>
        <input id="draft-project" v-model="form.project_name" class="field-input mt-1" placeholder="如：客户拜访打车" />
      </div>
      <div>
        <label class="field-label" for="draft-amount">金额</label>
        <input id="draft-amount" v-model="form.actual_amount" class="field-input mt-1" inputmode="decimal" />
      </div>
      <div>
        <label class="field-label">月份</label>
        <div class="mt-1 flex h-10 items-center rounded-md border border-slate-200 bg-slate-50 px-3 text-sm text-slate-700">
          {{ form.expense_month }}
        </div>
      </div>
      <div>
        <label class="field-label" for="draft-category">类别</label>
        <select id="draft-category" v-model="form.category" class="field-input mt-1">
          <option v-for="category in EXPENSE_CATEGORIES" :key="category">{{ category }}</option>
        </select>
      </div>
      <p v-if="error" class="rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-700">{{ error }}</p>
      <div class="flex justify-end">
        <button class="primary-button" type="submit" :disabled="saving">
          <Save class="h-4 w-4" />
          {{ saving ? "正在保存..." : "保存待补材料" }}
        </button>
      </div>
      </form>
    </section>
  </div>
</template>
