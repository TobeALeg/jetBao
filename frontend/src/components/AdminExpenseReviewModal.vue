<script setup lang="ts">
import { ref, watch } from "vue";
import { Loader2, X } from "lucide-vue-next";
import AttachmentPreviewModal from "./AttachmentPreviewModal.vue";
import UploadAttachmentTile from "./UploadAttachmentTile.vue";
import { getAdminExpenseReview } from "../services/api";
import { formatCurrency, formatDate } from "../utils/format";
import type { Attachment, ExpenseReviewDetail, LedgerRow } from "../types";

const props = defineProps<{
  row: LedgerRow | null;
  open: boolean;
}>();

const emit = defineEmits<{
  close: [];
  approve: [row: LedgerRow];
  reject: [row: LedgerRow];
}>();

const loading = ref(false);
const error = ref("");
const detail = ref<ExpenseReviewDetail | null>(null);
const previewAttachment = ref<Attachment | null>(null);

function statusLabel(status: string): string {
  if (status === "pending") return "待处理";
  if (status === "matched") return "已提交";
  if (status === "reviewed") return "已完成";
  return status;
}

async function loadDetail(expenseId: number) {
  loading.value = true;
  error.value = "";
  detail.value = null;
  try {
    detail.value = await getAdminExpenseReview(expenseId);
  } catch (err) {
    error.value = err instanceof Error ? err.message : "加载失败";
  } finally {
    loading.value = false;
  }
}

watch(
  () => [props.open, props.row?.id] as const,
  ([open, expenseId]) => {
    previewAttachment.value = null;
    if (!open || !expenseId) {
      detail.value = null;
      error.value = "";
      return;
    }
    void loadDetail(expenseId);
  },
  { immediate: true }
);

function openPreview(attachment: Attachment) {
  previewAttachment.value = attachment;
}

function closePreview() {
  previewAttachment.value = null;
}
</script>

<template>
  <div>
    <Teleport to="body">
    <div
      v-if="open && row"
      class="fixed inset-0 z-40 flex items-center justify-center bg-slate-900/70 p-4"
      @click.self="emit('close')"
    >
      <div class="relative flex max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden rounded-xl bg-white shadow-2xl">
        <div class="flex items-start justify-between border-b border-slate-200 px-5 py-4">
          <div class="min-w-0 pr-4">
            <h2 class="text-base font-semibold text-slate-900">审核预览</h2>
            <p class="mt-1 truncate text-sm text-slate-600">
              {{ row.employee_name }} · {{ row.project_name || row.note || "未命名" }} · {{ formatCurrency(row.actual_amount) }}
            </p>
          </div>
          <button
            class="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-slate-500 transition hover:bg-slate-100 hover:text-slate-800"
            type="button"
            @click="emit('close')"
          >
            <X class="h-4 w-4" />
          </button>
        </div>

        <div class="flex-1 overflow-y-auto px-5 py-4">
          <Loader2 v-if="loading" class="mx-auto my-10 h-8 w-8 animate-spin text-teal-700" />
          <p v-else-if="error" class="rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-700">{{ error }}</p>

          <div v-else-if="detail" class="space-y-5">
            <div class="grid gap-3 rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm sm:grid-cols-2">
              <div><span class="text-slate-500">类别：</span>{{ detail.category }}</div>
              <div><span class="text-slate-500">月份：</span>{{ detail.expense_month }}</div>
              <div><span class="text-slate-500">状态：</span>{{ statusLabel(detail.status) }}</div>
              <div><span class="text-slate-500">提交时间：</span>{{ formatDate(detail.created_at) }}</div>
              <div v-if="detail.is_substitute" class="sm:col-span-2">
                <span class="text-slate-500">替票说明：</span>{{ detail.substitute_reason || "无" }}
              </div>
              <div v-if="detail.note" class="sm:col-span-2">
                <span class="text-slate-500">备注：</span>{{ detail.note }}
              </div>
            </div>

            <section>
              <h3 class="mb-2 text-sm font-semibold text-slate-800">佐证材料</h3>
              <div v-if="detail.attachments.length" class="grid grid-cols-2 gap-2 sm:grid-cols-3">
                <UploadAttachmentTile
                  v-for="attachment in detail.attachments"
                  :key="attachment.id"
                  :attachment="attachment"
                  @preview="openPreview"
                />
              </div>
              <p v-else class="rounded-md border border-dashed border-slate-200 px-3 py-6 text-center text-sm text-slate-500">
                暂无佐证材料
              </p>
            </section>

            <section>
              <h3 class="mb-2 text-sm font-semibold text-slate-800">发票</h3>
              <div v-if="detail.invoice_attachments.length" class="grid grid-cols-2 gap-2 sm:grid-cols-3">
                <UploadAttachmentTile
                  v-for="attachment in detail.invoice_attachments"
                  :key="attachment.id"
                  :attachment="attachment"
                  @preview="openPreview"
                />
              </div>
              <p v-else class="rounded-md border border-dashed border-slate-200 px-3 py-6 text-center text-sm text-slate-500">
                暂无发票
              </p>
              <div v-if="detail.allocations.length" class="mt-3 space-y-1 text-xs text-slate-600">
                <p v-for="allocation in detail.allocations" :key="allocation.id">
                  {{ allocation.invoice_number || "发票" }} · {{ formatCurrency(allocation.allocated_amount) }}
                  <span v-if="allocation.invoice_buyer"> · {{ allocation.invoice_buyer }}</span>
                </p>
              </div>
            </section>
          </div>
        </div>

        <div
          v-if="detail && row.status === 'matched'"
          class="flex items-center justify-end gap-2 border-t border-slate-200 px-5 py-4"
        >
          <button class="secondary-button h-9" type="button" @click="emit('close')">关闭</button>
          <button class="h-9 rounded-md border border-amber-200 bg-amber-50 px-3 text-sm text-amber-700 transition hover:bg-amber-100" type="button" @click="emit('reject', row)">
            打回
          </button>
          <button class="primary-button h-9" type="button" @click="emit('approve', row)">
            通过
          </button>
        </div>
        <div v-else class="flex items-center justify-end border-t border-slate-200 px-5 py-4">
          <button class="secondary-button h-9" type="button" @click="emit('close')">关闭</button>
        </div>
      </div>
    </div>
    </Teleport>

    <AttachmentPreviewModal :attachment="previewAttachment" :open="Boolean(previewAttachment)" @close="closePreview" />
  </div>
</template>
