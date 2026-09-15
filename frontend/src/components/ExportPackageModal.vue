<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { Download, Loader2, X } from "lucide-vue-next";
import { COMPANY_ENTITIES } from "../constants/companyEntities";
import { downloadExportPackage, getExportPreview } from "../services/api";
import { formatCurrency, formatFileSize } from "../utils/format";
import type { ExportPreview } from "../types";

const props = defineProps<{
  open: boolean;
  initialMonth: string;
  initialCompanyEntity: string;
}>();

const emit = defineEmits<{
  close: [];
  complete: [filename: string];
}>();

const month = ref("");
const companyEntity = ref("");
const preview = ref<ExportPreview | null>(null);
const previewLoading = ref(false);
const previewError = ref("");
const exportError = ref("");
const exportPhase = ref<"idle" | "preparing" | "downloading" | "complete">("idle");
const receivedBytes = ref(0);
const totalBytes = ref(0);
let previewRequestId = 0;
let resettingSelection = false;

const exportFilters = computed(() => ({
  month: month.value,
  company_entity: companyEntity.value,
}));

const periodLabel = computed(() => {
  const [year, monthPart] = month.value.split("-");
  if (!year || !monthPart) return "未选择月份";
  return `${year} 年 ${Number(monthPart)} 月`;
});

const expectedFilename = computed(() => {
  const [year, monthPart] = month.value.split("-");
  if (!year || !monthPart) return "山途远智-报销明细.zip";
  return `山途远智-${year}年${Number(monthPart)}月-报销明细.zip`;
});

const progressPercent = computed(() => {
  if (!totalBytes.value) return null;
  return Math.min(100, Math.round((receivedBytes.value / totalBytes.value) * 100));
});

const isExporting = computed(() => exportPhase.value === "preparing" || exportPhase.value === "downloading");
const canExport = computed(() => Boolean(month.value && preview.value?.record_count && !previewLoading.value && !isExporting.value));

async function loadPreview() {
  if (!props.open || !month.value || isExporting.value) return;
  const requestId = ++previewRequestId;
  previewLoading.value = true;
  previewError.value = "";
  preview.value = null;
  try {
    const result = await getExportPreview(exportFilters.value);
    if (requestId === previewRequestId) preview.value = result;
  } catch (error) {
    if (requestId === previewRequestId) {
      previewError.value = error instanceof Error ? error.message : "无法读取导出预览";
    }
  } finally {
    if (requestId === previewRequestId) previewLoading.value = false;
  }
}

function close() {
  if (isExporting.value) return;
  emit("close");
}

async function startExport() {
  if (!canExport.value) return;
  exportError.value = "";
  exportPhase.value = "preparing";
  receivedBytes.value = 0;
  totalBytes.value = 0;
  try {
    const filename = await downloadExportPackage(exportFilters.value, (progress) => {
      exportPhase.value = "downloading";
      receivedBytes.value = progress.receivedBytes;
      totalBytes.value = progress.totalBytes;
    });
    exportPhase.value = "complete";
    emit("complete", filename);
  } catch (error) {
    exportPhase.value = "idle";
    exportError.value = error instanceof Error ? error.message : "导出失败，请重试";
  }
}

watch(
  () => props.open,
  (open) => {
    if (!open) return;
    resettingSelection = true;
    month.value = props.initialMonth;
    companyEntity.value = props.initialCompanyEntity;
    resettingSelection = false;
    preview.value = null;
    previewError.value = "";
    exportError.value = "";
    exportPhase.value = "idle";
    receivedBytes.value = 0;
    totalBytes.value = 0;
    void loadPreview();
  }
);

watch([month, companyEntity], () => {
  if (!props.open || resettingSelection) return;
  exportPhase.value = "idle";
  exportError.value = "";
  void loadPreview();
}, { flush: "sync" });
</script>

<template>
  <Teleport to="body">
    <div
      v-if="open"
      class="fixed inset-0 z-[60] flex items-center justify-center bg-slate-900/60 p-4"
      @click.self="close"
    >
      <div
        class="animate-scale-in relative flex w-full max-w-xl flex-col overflow-hidden rounded-panel bg-white shadow-overlay"
        role="dialog"
        aria-modal="true"
        aria-labelledby="export-package-title"
      >
        <div class="border-b border-hairline px-6 py-5">
          <button
            class="absolute right-4 top-4 inline-flex h-8 w-8 items-center justify-center rounded-control text-slate-500 transition duration-1 ease-standard hover:bg-surface-mute hover:text-slate-800 disabled:cursor-not-allowed disabled:opacity-40"
            type="button"
            aria-label="关闭"
            :disabled="isExporting"
            @click="close"
          >
            <X class="h-4 w-4" />
          </button>
          <h2 id="export-package-title" class="text-lg font-semibold text-slate-900">导出报销包</h2>
          <p class="mt-1 pr-8 text-sm text-slate-600">先确认报销月份。导出包只包含已提交和已完成记录。</p>
        </div>

        <div class="space-y-4 px-6 py-5">
          <div class="grid gap-3 sm:grid-cols-2">
            <div>
              <label class="field-label" for="export-month">报销月份</label>
              <input
                id="export-month"
                v-model="month"
                class="field-input mt-1 w-full"
                type="month"
                min="2026-01"
                required
                :disabled="isExporting"
              />
            </div>
            <div>
              <label class="field-label" for="export-company">公司主体</label>
              <select
                id="export-company"
                v-model="companyEntity"
                class="field-input mt-1 w-full"
                :disabled="isExporting"
              >
                <option value="">全部主体</option>
                <option v-for="company in COMPANY_ENTITIES" :key="company" :value="company">{{ company }}</option>
              </select>
            </div>
          </div>

          <div class="rounded-control border border-hairline bg-surface-soft p-4">
            <div v-if="previewLoading" class="flex items-center justify-center gap-2 py-4 text-sm text-slate-500">
              <Loader2 class="h-4 w-4 animate-spin" /> 正在核对可导出记录
            </div>
            <p v-else-if="previewError" class="text-sm text-state-danger-ink">{{ previewError }}</p>
            <template v-else-if="preview">
              <div class="grid grid-cols-3 gap-3">
                <div>
                  <p class="text-xs text-slate-500">导出期间</p>
                  <p class="mt-1 text-sm font-semibold text-slate-900">{{ periodLabel }}</p>
                </div>
                <div>
                  <p class="text-xs text-slate-500">可导出</p>
                  <p class="num mt-1 text-sm font-semibold text-slate-900">{{ preview.record_count }} 笔</p>
                </div>
                <div>
                  <p class="text-xs text-slate-500">报销金额</p>
                  <p class="num mt-1 text-sm font-semibold text-slate-900">{{ formatCurrency(preview.total_amount) }}</p>
                </div>
              </div>
              <p v-if="preview.pending_count" class="mt-3 border-t border-hairline pt-3 text-xs text-state-warn-ink">
                另有 {{ preview.pending_count }} 笔待补材料，不会进入本次导出。
              </p>
              <p v-else-if="!preview.record_count" class="mt-3 border-t border-hairline pt-3 text-xs text-slate-500">
                这个月份没有可导出的完整报销记录。
              </p>
            </template>
          </div>

          <div v-if="exportPhase !== 'idle'" class="rounded-control border border-accent-line bg-accent-soft p-4">
            <div class="flex items-center justify-between gap-3 text-sm text-accent-ink">
              <span v-if="exportPhase === 'preparing'" class="flex items-center gap-2">
                <Loader2 class="h-4 w-4 animate-spin" /> 正在整理 Excel 与附件，请勿关闭页面
              </span>
              <span v-else-if="exportPhase === 'downloading'" class="flex items-center gap-2">
                <Download class="h-4 w-4" /> 正在并行下载
              </span>
              <span v-else>下载已开始</span>
              <span v-if="exportPhase === 'downloading'" class="num shrink-0 text-xs">
                <template v-if="progressPercent !== null">{{ progressPercent }}%</template>
                <template v-else>{{ formatFileSize(receivedBytes) }}</template>
              </span>
            </div>
            <div v-if="exportPhase === 'downloading' && progressPercent !== null" class="mt-3 h-1.5 overflow-hidden rounded-full bg-white">
              <div class="h-full rounded-full bg-accent transition-[width] duration-2" :style="{ width: `${progressPercent}%` }"></div>
            </div>
          </div>

          <p v-if="exportError" class="rounded-control bg-state-danger-soft px-3 py-2 text-sm text-state-danger-ink">{{ exportError }}</p>

          <p class="text-xs text-slate-500">文件名：{{ expectedFilename }}</p>
        </div>

        <div class="flex items-center justify-end gap-2 border-t border-hairline px-6 py-4">
          <button class="secondary-button h-10" type="button" :disabled="isExporting" @click="close">
            {{ exportPhase === "complete" ? "完成" : "取消" }}
          </button>
          <button
            v-if="exportPhase !== 'complete'"
            class="primary-button h-10"
            type="button"
            :disabled="!canExport"
            @click="startExport"
          >
            <Loader2 v-if="isExporting" class="h-4 w-4 animate-spin" />
            <Download v-else class="h-4 w-4" />
            {{ isExporting ? "正在导出" : `导出 ${periodLabel}` }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
