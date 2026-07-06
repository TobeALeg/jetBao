<script setup lang="ts">
import { ClipboardList, Download } from "lucide-vue-next";
import { formatCurrency } from "../utils/format";
import type { ExportPreview } from "../types";

defineProps<{
  preview: ExportPreview | null;
  loading?: boolean;
  exporting?: boolean;
}>();

defineEmits<{
  export: [];
  "show-drafts": [];
}>();
</script>

<template>
  <section class="tool-panel overflow-hidden rounded-lg">
    <div class="border-b border-slate-200 px-5 py-4">
      <h2 class="section-title">导出预览</h2>
      <p class="muted mt-1">导出前先确认范围和汇总金额。</p>
    </div>
    <div v-if="loading" class="px-5 py-12 text-center text-sm text-slate-500">正在计算...</div>
    <div v-else-if="preview" class="divide-y divide-slate-200">
      <div class="grid divide-y divide-slate-200 sm:grid-cols-2 sm:divide-x sm:divide-y-0 lg:grid-cols-4">
        <div class="px-5 py-5">
          <div class="text-xs text-slate-500">人数</div>
          <div class="mt-1 text-2xl font-semibold text-ink">{{ preview.employee_count }}</div>
        </div>
        <div class="px-5 py-5">
          <div class="text-xs text-slate-500">笔数</div>
          <div class="mt-1 text-2xl font-semibold text-ink">{{ preview.record_count }}</div>
        </div>
        <div class="px-5 py-5">
          <div class="text-xs text-slate-500">总金额</div>
          <div class="mt-1 text-2xl font-semibold text-ink">{{ formatCurrency(preview.total_amount) }}</div>
        </div>
        <div class="px-5 py-5">
          <div class="text-xs text-slate-500">待补材料</div>
          <div class="mt-1 text-2xl font-semibold" :class="preview.pending_draft_count ? 'text-amber-700' : 'text-ink'">
            {{ preview.pending_draft_count }}
          </div>
        </div>
      </div>
      <div class="flex flex-col justify-between gap-3 px-5 py-4 sm:flex-row sm:items-center">
        <button
          class="secondary-button"
          type="button"
          :disabled="!preview.pending_draft_count"
          @click="$emit('show-drafts')"
        >
          <ClipboardList class="h-4 w-4" />
          查看待补材料
        </button>
        <button class="primary-button" type="button" :disabled="exporting || !preview.record_count" @click="$emit('export')">
          <Download class="h-4 w-4" />
          {{ exporting ? "正在导出..." : "导出 Excel" }}
        </button>
      </div>
    </div>
    <div v-else class="empty-state">
      <div class="text-sm font-medium text-slate-700">请选择月份和公司主体</div>
      <div class="text-xs text-slate-500">选择后系统会自动计算导出范围。</div>
    </div>
  </section>
</template>
