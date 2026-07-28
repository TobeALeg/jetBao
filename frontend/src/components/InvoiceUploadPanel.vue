<script setup lang="ts">
import { computed, ref } from "vue";
import { AlertTriangle, CheckCircle2, ChevronDown, ChevronUp, FileUp, Image, Loader2 } from "lucide-vue-next";
import { uploadAttachments } from "../services/api";
import { buyerMatchStatus, isDifferentAllowedBuyer } from "../constants/companyEntities";
import { formatCurrency, formatFileSize } from "../utils/format";
import type { Attachment } from "../types";

const props = defineProps<{
  attachments: Attachment[];
  currentCompany: string;
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
const expandedIds = ref(new Set<number>());

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

function invoiceBuyerStatus(item: Record<string, unknown>): string {
  const buyer = invoiceText(item, "buyer");
  if (buyer === "-") return "未识别抬头";
  const status = buyerMatchStatus(buyer);
  if (status === "partial") return `${buyer}（需确认）`;
  if (status === "none") return `${buyer}（不可用）`;
  return isDifferentAllowedBuyer(buyer, props.currentCompany) ? `${buyer}（可用抬头）` : buyer;
}

function invoiceBuyerTone(item: Record<string, unknown>): "ok" | "warn" | "danger" {
  const buyer = invoiceText(item, "buyer");
  const status = buyer === "-" ? "none" : buyerMatchStatus(buyer);
  if (status === "exact" && !isDifferentAllowedBuyer(buyer, props.currentCompany)) return "ok";
  if (status === "exact" || status === "partial") return "warn";
  return "danger";
}

function toggleExpanded(id: number) {
  const next = new Set(expandedIds.value);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  expandedIds.value = next;
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
  <div class="flex min-h-64 flex-col gap-3">
    <button
      class="flex w-full flex-col items-center justify-center rounded-lg border border-dashed px-4 text-center transition"
      style="height: 175px"
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
        {{ uploading ? uploadingLabel : dragging ? "松开上传" : "拖拽或点击上传发票" }}
      </span>
      <span class="mt-1 text-xs text-slate-500">PDF / 图片，上传后自动识别</span>
    </button>
    <input ref="inputRef" class="hidden" type="file" accept="image/*,.pdf" multiple @change="handleFileChange" />

    <button class="secondary-button w-full justify-center" type="button" :disabled="uploading || pooling || !attachments.length" @click="$emit('addToPool')">
      <Loader2 v-if="uploading || pooling" class="h-4 w-4 animate-spin" />
      <FileUp v-else class="h-4 w-4" />
      {{ pooling ? "正在加入..." : "加入发票池" }}
    </button>

    <p v-if="error" class="rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-700">{{ error }}</p>

    <div v-if="duplicateAttachments.length" class="space-y-1 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
      <div>{{ duplicateAttachments.length }} 个附件疑似重复：</div>
      <div v-for="att in duplicateAttachments" :key="att.id" class="pl-2">
        {{ att.original_filename }}<span v-if="att.duplicate_of?.length"> 与 {{ att.duplicate_of.map((d) => `${d.employee_name} 的 ${d.filename}`).join("、") }} 重复</span>
      </div>
    </div>

    <div v-if="allInvoiceItems.length" class="flex items-center gap-3 rounded-md border border-teal-100 bg-teal-50 px-3 py-2 text-xs text-teal-800">
      <span>已识别 <strong>{{ allInvoiceItems.length }}</strong> 条</span>
      <span>合计 <strong>{{ formatCurrency(recognizedAmountTotal) }}</strong></span>
    </div>

    <div v-for="attachment in attachments" :key="attachment.id" class="rounded-lg border border-slate-200 bg-white">
      <div class="flex items-center gap-3 p-3">
        <div class="grid h-12 w-12 shrink-0 place-items-center overflow-hidden rounded-md bg-slate-100">
          <img
            v-if="attachment.preview_url"
            :src="attachment.preview_url"
            :alt="attachment.original_filename"
            class="h-full w-full object-cover"
          />
          <Image v-else class="h-4 w-4 text-slate-400" />
        </div>
        <div class="min-w-0 flex-1">
          <div class="truncate text-sm font-medium text-slate-900">{{ attachment.original_filename }}</div>
          <div class="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-slate-500">
            <span>{{ formatFileSize(attachment.file_size) }}</span>
            <span
              class="status-pill"
              :class="ocrStatusClass(attachment.ocr_status)"
            >
              {{ ocrStatusLabel(attachment.ocr_status) }}
            </span>
            <span v-if="attachment.is_duplicate" class="status-pill bg-amber-50 text-amber-700">
              重复
            </span>
          </div>
        </div>
        <button
          v-if="invoiceItemsOf(attachment).length"
          class="grid h-7 w-7 shrink-0 place-items-center rounded-md text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
          type="button"
          :title="expandedIds.has(attachment.id) ? '收起详情' : '展开详情'"
          @click="toggleExpanded(attachment.id)"
        >
          <ChevronDown v-if="!expandedIds.has(attachment.id)" class="h-4 w-4" />
          <ChevronUp v-else class="h-4 w-4" />
        </button>
        <button
          class="inline-flex h-7 shrink-0 items-center rounded-md px-2 text-xs text-slate-500 transition hover:bg-rose-50 hover:text-rose-700 disabled:cursor-not-allowed disabled:text-slate-300"
          type="button"
          :disabled="removingId === attachment.id"
          @click="$emit('remove', attachment.id)"
        >
          <Loader2 v-if="removingId === attachment.id" class="h-3.5 w-3.5 animate-spin" />
          {{ removingId === attachment.id ? "删除中" : "删除" }}
        </button>
      </div>
      <div v-if="expandedIds.has(attachment.id)" class="space-y-2 border-t border-slate-100 px-3 py-3 text-xs text-slate-500">
        <p>{{ messageOf(attachment) }}</p>
        <p v-if="errorOf(attachment)" class="text-rose-700">{{ errorOf(attachment) }}</p>
        <div
          v-if="suggestedAmountOf(attachment) !== null"
          class="inline-flex items-center rounded-md bg-teal-50 px-2 py-1 font-medium text-teal-800"
        >
          建议金额：{{ formatCurrency(suggestedAmountOf(attachment)) }}
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
              <div>发票号码：{{ invoiceText(item, "invoice_number") }}</div>
              <div>销售方：{{ invoiceText(item, "seller") }}</div>
              <div class="flex items-center justify-end gap-1.5 sm:justify-start">
                <span
                  :class="{
                    'text-teal-700': invoiceBuyerTone(item) === 'ok',
                    'text-amber-700': invoiceBuyerTone(item) === 'warn',
                    'text-rose-700': invoiceBuyerTone(item) === 'danger'
                  }"
                >
                  购买方：{{ invoiceBuyerStatus(item) }}
                </span>
                <CheckCircle2 v-if="invoiceBuyerTone(item) === 'ok'" class="h-3.5 w-3.5 text-teal-700" />
                <AlertTriangle v-else class="h-3.5 w-3.5" :class="invoiceBuyerTone(item) === 'warn' ? 'text-amber-600' : 'text-rose-600'" />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
