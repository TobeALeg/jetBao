<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from "vue";
import { FileText, Loader2, X } from "lucide-vue-next";
import { getAttachmentObjectUrl } from "../services/api";
import { looksLikeImage, looksLikePdf } from "../utils/attachmentUtils";
import type { Attachment } from "../types";

const props = defineProps<{
  attachment: Attachment | null;
  open: boolean;
}>();

const emit = defineEmits<{
  close: [];
}>();

const loading = ref(false);
const previewUrl = ref("");
const contentType = ref("");
const failed = ref(false);
let ownedUrl = "";

function resetPreview() {
  if (ownedUrl) {
    URL.revokeObjectURL(ownedUrl);
    ownedUrl = "";
  }
  previewUrl.value = "";
  contentType.value = "";
  failed.value = false;
  loading.value = false;
}

async function loadPreview(attachment: Attachment) {
  resetPreview();
  if (attachment.preview_url) {
    previewUrl.value = attachment.preview_url;
    contentType.value = looksLikePdf(attachment.original_filename) ? "application/pdf" : "image/*";
    return;
  }

  loading.value = true;
  try {
    const preview = await getAttachmentObjectUrl(attachment.id);
    previewUrl.value = preview.url;
    contentType.value = preview.contentType;
    ownedUrl = preview.url;
  } catch {
    failed.value = true;
  } finally {
    loading.value = false;
  }
}

watch(
  () => [props.open, props.attachment?.id] as const,
  ([open, attachmentId]) => {
    if (!open || !attachmentId || !props.attachment) {
      resetPreview();
      return;
    }
    void loadPreview(props.attachment);
  },
  { immediate: true }
);

onBeforeUnmount(resetPreview);

const isImagePreview = () =>
  contentType.value.startsWith("image/") || (props.attachment ? looksLikeImage(props.attachment.original_filename) : false);

const isPdfPreview = () =>
  contentType.value === "application/pdf" || (props.attachment ? looksLikePdf(props.attachment.original_filename) : false);
</script>

<template>
  <Teleport to="body">
    <div
      v-if="open && attachment"
      class="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/70 p-4"
      @click.self="emit('close')"
    >
      <div class="relative flex max-h-[90vh] w-full max-w-5xl flex-col overflow-hidden rounded-xl bg-white shadow-2xl">
        <div class="flex items-center justify-between border-b border-slate-200 px-4 py-3">
          <p class="truncate pr-4 text-sm font-medium text-slate-800">{{ attachment.original_filename }}</p>
          <button
            class="inline-flex h-8 w-8 items-center justify-center rounded-md text-slate-500 transition hover:bg-slate-100 hover:text-slate-800"
            type="button"
            @click="emit('close')"
          >
            <X class="h-4 w-4" />
          </button>
        </div>

        <div class="flex min-h-[240px] flex-1 items-center justify-center overflow-auto bg-slate-100 p-4">
          <Loader2 v-if="loading" class="h-8 w-8 animate-spin text-teal-700" />
          <div v-else-if="failed" class="text-center text-sm text-slate-500">
            <FileText class="mx-auto mb-2 h-10 w-10 text-slate-400" />
            预览加载失败
          </div>
          <img
            v-else-if="isImagePreview() && previewUrl"
            :src="previewUrl"
            :alt="attachment.original_filename"
            class="max-h-[75vh] max-w-full object-contain"
          />
          <iframe
            v-else-if="isPdfPreview() && previewUrl"
            :src="previewUrl"
            class="h-[75vh] w-full rounded-md border border-slate-200 bg-white"
            title="PDF 预览"
          />
          <div v-else class="text-center text-sm text-slate-500">
            <FileText class="mx-auto mb-2 h-10 w-10 text-slate-400" />
            暂不支持预览此文件类型
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>
