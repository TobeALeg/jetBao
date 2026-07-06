<script setup lang="ts">
import { onMounted, ref } from "vue";
import ExportPreviewPanel from "../components/ExportPreview.vue";
import { downloadExport, downloadExportPackage, getExportPreview } from "../services/api";
import { currentMonth } from "../utils/format";
import type { ExportPreview } from "../types";

defineEmits<{
  "show-drafts": [];
}>();

const filters = ref<Record<string, string>>({
  month: currentMonth(),
  company_entity: ""
});

const preview = ref<ExportPreview | null>(null);
const loading = ref(false);
const exporting = ref(false);
const exportingPackage = ref(false);
const error = ref("");

async function loadPreview() {
  loading.value = true;
  error.value = "";
  try {
    preview.value = await getExportPreview(filters.value);
  } catch (err) {
    error.value = err instanceof Error ? err.message : "加载导出预览失败";
  } finally {
    loading.value = false;
  }
}

async function exportFile() {
  exporting.value = true;
  error.value = "";
  try {
    await downloadExport(filters.value);
  } catch (err) {
    error.value = err instanceof Error ? err.message : "导出失败";
  } finally {
    exporting.value = false;
  }
}

async function exportPackage() {
  exportingPackage.value = true;
  error.value = "";
  try {
    await downloadExportPackage(filters.value);
  } catch (err) {
    error.value = err instanceof Error ? err.message : "导出明细包失败";
  } finally {
    exportingPackage.value = false;
  }
}

onMounted(loadPreview);
</script>

<template>
  <div class="mx-auto max-w-4xl space-y-5">
    <div>
      <h1 class="page-title">导出</h1>
      <p class="muted mt-1">选择月份和公司主体后导出台账或完整附件包。</p>
    </div>

    <div class="guide-hint">
      <span>提示：</span>
      <span>导出的 Excel 仅包含「已提交」的记录。「待补材料」的草稿不会进入导出文件。</span>
    </div>

    <section class="tool-panel rounded-lg p-5">
      <div class="grid gap-4 sm:grid-cols-2">
        <div>
          <label class="field-label" for="export-month">月份</label>
          <input id="export-month" v-model="filters.month" class="field-input mt-1" type="month" @change="loadPreview" />
        </div>
        <div>
          <label class="field-label" for="export-company">公司主体</label>
          <input
            id="export-company"
            v-model="filters.company_entity"
            class="field-input mt-1"
            placeholder="留空导出全部公司"
            @change="loadPreview"
          />
        </div>
      </div>
      <div class="mt-4 flex justify-end">
        <button class="secondary-button" type="button" @click="loadPreview">刷新预览</button>
      </div>
    </section>

    <p v-if="error" class="rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-700">{{ error }}</p>
    <ExportPreviewPanel
      :preview="preview"
      :loading="loading"
      :exporting="exporting"
      :exporting-package="exportingPackage"
      @export="exportFile"
      @export-package="exportPackage"
      @show-drafts="$emit('show-drafts')"
    />
  </div>
</template>
