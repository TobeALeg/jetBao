<script setup lang="ts">
import { AlertTriangle, FileText, Upload } from "lucide-vue-next";
import ExpenseAttachmentUploadButton from "./ExpenseAttachmentUploadButton.vue";
import { formatCurrency, formatDate } from "../utils/format";
import type { Expense } from "../types";

defineProps<{
  expenses: Expense[];
  loading?: boolean;
}>();

defineEmits<{
  "complete-draft": [expense: Expense];
  "attachment-uploaded": [expense: Expense];
  "upload-error": [message: string];
}>();

function statusLabel(status: Expense["status"]): string {
  return status === "draft" ? "待补材料" : "已提交";
}

function statusClass(status: Expense["status"]): string {
  return status === "draft" ? "bg-amber-50 text-amber-700" : "bg-teal-50 text-teal-700";
}
</script>

<template>
  <div class="tool-panel overflow-hidden rounded-lg">
    <div class="flex items-center justify-between border-b border-slate-200 px-5 py-4">
      <div>
        <h2 class="section-title">报销记录</h2>
        <p class="muted mt-1">按提交时间倒序排列</p>
      </div>
    </div>

    <div v-if="loading" class="px-5 py-12 text-center text-sm text-slate-500">正在加载...</div>
    <div v-else-if="!expenses.length" class="empty-state">
      <div class="empty-state-icon">
        <FileText class="h-6 w-6" />
      </div>
      <div>
        <div class="text-sm font-medium text-slate-700">还没有报销记录</div>
        <div class="mt-1 text-xs text-slate-500">回到首页点「记一笔」开始录入第一笔报销。</div>
      </div>
    </div>

    <div v-else class="overflow-x-auto">
      <table class="min-w-full divide-y divide-slate-200 text-left text-sm">
        <thead class="bg-slate-50 text-xs font-medium uppercase tracking-normal text-slate-500">
          <tr>
            <th class="px-5 py-3">月份</th>
            <th class="px-5 py-3">项目</th>
            <th class="px-5 py-3">类别</th>
            <th class="px-5 py-3">金额</th>
            <th class="px-5 py-3">替票</th>
            <th class="px-5 py-3">附件</th>
            <th class="px-5 py-3">状态</th>
            <th class="px-5 py-3">提交时间</th>
            <th class="px-5 py-3">操作</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100 bg-white">
          <tr v-for="expense in expenses" :key="expense.id" class="hover:bg-slate-50/70">
            <td class="whitespace-nowrap px-5 py-4 font-medium text-slate-900">{{ expense.expense_month }}</td>
            <td class="min-w-48 px-5 py-4 text-slate-700">{{ expense.project_name || expense.note || "-" }}</td>
            <td class="whitespace-nowrap px-5 py-4 text-slate-700">{{ expense.category }}</td>
            <td class="whitespace-nowrap px-5 py-4 font-medium text-slate-900">
              {{ formatCurrency(expense.actual_amount) }}
            </td>
            <td class="whitespace-nowrap px-5 py-4">
              <span
                class="status-pill"
                :class="expense.is_substitute ? 'bg-amber-50 text-amber-700' : 'bg-slate-100 text-slate-600'"
              >
                {{ expense.is_substitute ? "是" : "否" }}
              </span>
            </td>
            <td class="px-5 py-4">
              <div class="flex items-center gap-2 text-slate-600">
                <FileText class="h-4 w-4" />
                <span>{{ expense.attachments.length }}</span>
                <span v-if="expense.has_duplicate" class="inline-flex items-center gap-1 text-amber-700">
                  <AlertTriangle class="h-4 w-4" />
                  疑似重复
                </span>
              </div>
            </td>
            <td class="whitespace-nowrap px-5 py-4">
              <span class="status-pill" :class="statusClass(expense.status)">{{ statusLabel(expense.status) }}</span>
            </td>
            <td class="whitespace-nowrap px-5 py-4 text-slate-500">{{ formatDate(expense.created_at) }}</td>
            <td class="whitespace-nowrap px-5 py-4">
              <div v-if="expense.status === 'draft'" class="flex items-center gap-2">
                <ExpenseAttachmentUploadButton
                  :expense="expense"
                  compact
                  label="附件"
                  @uploaded="$emit('attachment-uploaded', $event)"
                  @error="$emit('upload-error', $event)"
                />
                <button
                  class="secondary-button h-8 px-2 text-xs"
                  type="button"
                  @click="$emit('complete-draft', expense)"
                >
                  <Upload class="h-4 w-4" />
                  补材料
                </button>
              </div>
              <span v-else class="text-sm text-slate-400">-</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
