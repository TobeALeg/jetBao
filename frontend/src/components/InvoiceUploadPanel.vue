<script setup lang="ts">
import { computed, ref } from "vue";
import { AlertTriangle, CheckCircle2, FileUp, Image, Loader2 } from "lucide-vue-next";
import { uploadAttachments } from "../services/api";
import { formatCurrency, formatFileSize } from "../utils/format";
import type { Attachment } from "../types";

const props = defineProps<{
  attachments: Attachment[];
  removingId?: number | null;
  pooling?: boolean;
}>();

const emit = defineEmits<{
  uploaded: [attachments: Attachment[]];
  addToPool: [];
  remove: [id: number];
}>();

const uploading = ref(false);
const uploadingLabel = ref("");
const error = ref("");
const dragging = ref(false);
const dragDepth = ref(0);
const inputRef = ref<HTMLInputElement | null>(null);

const duplicateAttachments = computed(() => props.attachments.filter((item) => item.is_duplicate));
const allInvoiceItems = computed(() => props.attachments.flatMap((attachment) => invoiceItemsOf(attachment)));
const recognizedAmountTotal = computed(() =>
  allInvoiceItems.value.reduce((sum, item) => {
    const amount = item.amount;
    return typeof amount === "number" ? sum + amount : sum;
  }, 0)
);

function ocrStatusLabel(status: string): string {
  if (status === "success") return "OCR 已识别";
  if (status === "failed") return "OCR 失败";
  if (status === "not_configured") return "OCR 未配置";
  return "需手动确认";
}

function ocrStatusClass(status: string): string {
  if (status === "success") return "bg-teal-50 text-teal-700";
  if (status === "failed") return "bg-rose-50 text-rose-700";
  return "bg-amber-50 text-amber-700";
}

function isOcrWarning(status: string): boolean {
  return status !== "success";
}

function messageOf(attachment: Attachment): string {
  const message = attachment.ocr_result.message;
  return typeof message === "string" ? message : "OCR 结果待确认";
}

function errorOf(attachment: Attachment): string {
  const error = attachment.ocr_result.error;
  return typeof error === "string" ? error : "";
}

function suggestedAmountOf(attachment: Attachment): number | null {
  const value = attachment.ocr_result.suggested_invoice_amount;
  return typeof value === "number" ? value : null;
}

function textLinesOf(attachment: Attachment): string[] {
  const lines = attachment.ocr_result.text_lines;
  if (!Array.isArray(lines)) return [];
  return lines
    .map((line) => {
      if (line && typeof line === "object" && "text" in line && typeof line.text === "string") return line.text;
      return "";
    })
    .filter(Boolean)
    .slice(0, 6);
}

function invoiceItemsOf(attachment: Attachment): Array<Record<string, unknown>> {
  const items = attachment.ocr_result.invoice_items;
  return Array.isArray(items) ? (items as Array<Record<string, unknown>>) : [];
}

function invoiceText(item: Record<string, unknown>, key: string): string {
  const value = item[key];
  if (value === null || value === undefined || value === "") return "-";
  return String(value);
}

function invoiceLabel(item: Record<string, unknown>): string {
  const subType = item.sub_type_description;
  const type = item.type_description;
  if (typeof subType === "string" && subType) return subType;
  if (typeof type === "string" && type) return type;
  return "票据";
}

function invoiceAmount(item: Record<string, unknown>): string {
  const value = item.amount;
  return typeof value === "number" ? formatCurrency(value) : "-";
}

async function uploadFiles(files: File[]) {
  const allowedFiles = files.filter(isAllowedInvoiceFile);
  if (!allowedFiles.length) {
    error.value = "请选择 PDF 或图片文件。";
    return;
  }
  uploading.value = true;
  uploadingLabel.value = allowedFiles.length > 1 ? `正在上传并识别 ${allowedFiles.length} 个附件...` : "正在上传并识别...";
  error.value = "";
  try {
    const attachments = await uploadAttachments(allowedFiles);
    const uploaded = attachments.map((attachment, index) => {
      const file = allowedFiles[index];
      const previewUrl = file?.type.startsWith("image/") ? URL.createObjectURL(file) : "";
      return { ...attachment, preview_url: previewUrl };
    });
    emit("uploaded", uploaded);
  } catch (err) {
    error.value = err instanceof Error ? err.message : "上传失败";
  } finally {
    uploading.value = false;
    uploadingLabel.value = "";
  }
}

function isAllowedInvoiceFile(file: File): boolean {
  return file.type.startsWith("image/") || file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
}

async function handleFileChange(event: Event) {
  const input = event.target as HTMLInputElement;
  await uploadFiles(Array.from(input.files ?? []));
  input.value = "";
}

function handleDragEnter() {
  dragDepth.value += 1;
  dragging.value = true;
}

function handleDragOver(event: DragEvent) {
  if (event.dataTransfer) event.dataTransfer.dropEffect = "copy";
  dragging.value = true;
}

function handleDragLeave() {
  dragDepth.value = Math.max(0, dragDepth.value - 1);
  dragging.value = dragDepth.value > 0;
}

async function handleDrop(event: DragEvent) {
  dragDepth.value = 0;
  dragging.value = false;
  const files = Array.from(event.dataTransfer?.files ?? []).filter(isAllowedInvoiceFile);
  if (!files.length) {
    error.value = "请拖入 PDF 或图片文件。";
    return;
  }
  await uploadFiles(files);
}
</script>

<template>
  <section class="tool-panel rounded-lg">
    <div class="border-b border-slate-200 px-5 py-4">
      <h2 class="section-title">上传发票附件</h2>
      <p class="muted mt-1">拖拽或点击上传，支持 PDF 和图片，上传后自动识别票据条目。</p>
    </div>

    <div class="space-y-4 p-5">
      <button
        class="flex min-h-36 w-full flex-col items-center justify-center rounded-lg border border-dashed px-4 text-center transition"
        :class="dragging ? 'border-teal-600 bg-teal-50' : 'border-slate-300 bg-slate-50 hover:border-teal-600 hover:bg-teal-50/40'"
        type="button"
        :disabled="uploading"
        @click="inputRef?.click()"
        @dragenter.prevent="handleDragEnter"
        @dragover.prevent="handleDragOver"
        @dragleave.prevent="handleDragLeave"
        @drop.prevent="handleDrop"
      >
        <Loader2 v-if="uploading" class="h-6 w-6 animate-spin text-teal-700" />
        <FileUp v-else class="h-6 w-6 text-teal-700" />
        <span class="mt-3 text-sm font-medium text-slate-800">
          {{ uploading ? uploadingLabel : dragging ? "松开上传这些发票" : "拖拽或点击上传发票" }}
        </span>
        <span class="mt-1 text-xs text-slate-500">可一次拖入或选择多个 PDF / 图片，上传后先解析，再由按钮决定去向</span>
      </button>
      <input ref="inputRef" class="hidden" type="file" accept="image/*,.pdf" multiple @change="handleFileChange" />

      <button class="secondary-button w-full justify-center" type="button" :disabled="uploading || pooling || !attachments.length" @click="$emit('addToPool')">
        <Loader2 v-if="uploading || pooling" class="h-4 w-4 animate-spin" />
        <FileUp v-else class="h-4 w-4" />
        {{ pooling ? "正在加入..." : "加入发票池" }}
      </button>

      <p v-if="error" class="rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-700">{{ error }}</p>

      <div v-if="duplicateAttachments.length" class="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
        有 {{ duplicateAttachments.length }} 个附件疑似重复。系统只提醒，不会阻止提交。
      </div>

      <div v-if="allInvoiceItems.length" class="grid gap-3 rounded-lg border border-teal-100 bg-teal-50 p-3 text-sm sm:grid-cols-2">
        <div>
          <div class="text-xs text-teal-700">已识别票据条目</div>
          <div class="mt-1 text-xl font-semibold text-teal-950">{{ allInvoiceItems.length }}</div>
        </div>
        <div>
          <div class="text-xs text-teal-700">识别金额合计</div>
          <div class="mt-1 text-xl font-semibold text-teal-950">{{ formatCurrency(recognizedAmountTotal) }}</div>
        </div>
      </div>

      <div v-if="!attachments.length" class="guide-hint mt-2">
        上传发票后，可以加入发票池，也可以随当前花费一起记录。
      </div>

      <div v-for="attachment in attachments" :key="attachment.id" class="rounded-lg border border-slate-200 bg-white">
        <div class="flex gap-3 p-3">
          <div class="grid h-16 w-16 shrink-0 place-items-center overflow-hidden rounded-md bg-slate-100">
            <img
              v-if="attachment.preview_url"
              :src="attachment.preview_url"
              :alt="attachment.original_filename"
              class="h-full w-full object-cover"
            />
            <Image v-else class="h-5 w-5 text-slate-400" />
          </div>
          <div class="min-w-0 flex-1">
            <div class="truncate text-sm font-medium text-slate-900">{{ attachment.original_filename }}</div>
            <div class="mt-1 text-xs text-slate-500">{{ formatFileSize(attachment.file_size) }}</div>
            <div class="mt-2 flex flex-wrap items-center gap-2">
              <span
                class="status-pill"
                :class="ocrStatusClass(attachment.ocr_status)"
              >
                <AlertTriangle
                  v-if="isOcrWarning(attachment.ocr_status)"
                  class="mr-1 h-3.5 w-3.5"
                />
                <CheckCircle2 v-else class="mr-1 h-3.5 w-3.5" />
                {{ ocrStatusLabel(attachment.ocr_status) }}
              </span>
              <span v-if="attachment.is_duplicate" class="status-pill bg-amber-50 text-amber-700">
                疑似重复 {{ attachment.duplicate_count }} 次
              </span>
            </div>
          </div>
          <button
            class="inline-flex h-8 shrink-0 items-center gap-1 rounded-md px-2 text-sm text-slate-500 transition hover:bg-rose-50 hover:text-rose-700 disabled:cursor-not-allowed disabled:text-slate-300"
            type="button"
            :disabled="removingId === attachment.id"
            @click="$emit('remove', attachment.id)"
          >
            <Loader2 v-if="removingId === attachment.id" class="h-3.5 w-3.5 animate-spin" />
            {{ removingId === attachment.id ? "删除中" : "删除" }}
          </button>
        </div>
        <div class="space-y-2 border-t border-slate-100 px-3 py-3 text-xs text-slate-500">
          <p>{{ messageOf(attachment) }}</p>
          <p v-if="errorOf(attachment)" class="text-rose-700">{{ errorOf(attachment) }}</p>
          <div
            v-if="suggestedAmountOf(attachment) !== null"
            class="inline-flex items-center rounded-md bg-teal-50 px-2 py-1 font-medium text-teal-800"
          >
            建议发票金额：{{ formatCurrency(suggestedAmountOf(attachment)) }}
          </div>
          <div v-if="textLinesOf(attachment).length" class="rounded-md bg-slate-50 px-3 py-2">
            <div class="mb-1 font-medium text-slate-700">识别文本</div>
            <p v-for="line in textLinesOf(attachment)" :key="line" class="truncate leading-5">{{ line }}</p>
          </div>
          <div v-if="invoiceItemsOf(attachment).length" class="overflow-hidden rounded-md border border-slate-200">
            <div class="border-b border-slate-200 bg-slate-50 px-3 py-2 font-medium text-slate-700">
              票据条目（{{ invoiceItemsOf(attachment).length }}）
            </div>
            <div class="divide-y divide-slate-100">
              <div v-for="(item, index) in invoiceItemsOf(attachment)" :key="`${attachment.id}-${index}`" class="grid gap-1 px-3 py-2 sm:grid-cols-2">
                <div class="font-medium text-slate-800">{{ invoiceLabel(item) }}</div>
                <div class="text-right font-medium text-slate-900 sm:text-right">{{ invoiceAmount(item) }}</div>
                <div>页码：{{ invoiceText(item, "page") }}</div>
                <div>日期：{{ invoiceText(item, "date") }}</div>
                <div>号码：{{ invoiceText(item, "invoice_number") }}</div>
                <div>销售方：{{ invoiceText(item, "seller") }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
