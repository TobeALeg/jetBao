<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from "vue";
import { FileImage } from "lucide-vue-next";
import type {
  PDFDocumentLoadingTask,
  RenderTask,
} from "pdfjs-dist";
import pdfWorkerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { getAttachmentObjectUrl } from "../services/api";
import { looksLikeImage, looksLikePdf } from "../utils/attachmentUtils";
import type { Attachment } from "../types";

const props = defineProps<{
  attachment: Attachment;
  large?: boolean;
}>();

const previewUrl = ref(props.attachment.preview_url ?? "");
const pdfCanvas = ref<HTMLCanvasElement | null>(null);
const pdfPreview = ref(false);
const failed = ref(false);
let ownedUrl = "";
let loadVersion = 0;
let pdfLoadingTask: PDFDocumentLoadingTask | null = null;
let pdfRenderTask: RenderTask | null = null;

function resetPreview() {
  loadVersion += 1;
  pdfRenderTask?.cancel();
  pdfRenderTask = null;
  void pdfLoadingTask?.destroy();
  pdfLoadingTask = null;
  if (ownedUrl) URL.revokeObjectURL(ownedUrl);
  ownedUrl = "";
  previewUrl.value = "";
  pdfPreview.value = false;
  failed.value = false;
}

async function renderPdf(url: string, version: number) {
  pdfPreview.value = true;
  await nextTick();
  if (version !== loadVersion || !pdfCanvas.value) return;

  const { GlobalWorkerOptions, getDocument } = await import("pdfjs-dist");
  if (version !== loadVersion || !pdfCanvas.value) return;
  GlobalWorkerOptions.workerSrc = pdfWorkerUrl;
  const loadingTask = getDocument({ url });
  pdfLoadingTask = loadingTask;
  const document = await loadingTask.promise;
  if (version !== loadVersion) {
    await loadingTask.destroy();
    return;
  }

  const page = await document.getPage(1);
  const baseViewport = page.getViewport({ scale: 1 });
  const targetWidth = props.large ? 640 : 128;
  const viewport = page.getViewport({ scale: targetWidth / baseViewport.width });
  const canvas = pdfCanvas.value;
  canvas.width = Math.ceil(viewport.width);
  canvas.height = Math.ceil(viewport.height);
  pdfRenderTask = page.render({ canvas, viewport, background: "#ffffff" });
  await pdfRenderTask.promise;
}

async function loadPreview() {
  resetPreview();
  const version = loadVersion;
  try {
    if (props.attachment.preview_url) {
      if (looksLikePdf(props.attachment.original_filename)) {
        await renderPdf(props.attachment.preview_url, version);
      } else {
        previewUrl.value = props.attachment.preview_url;
      }
      return;
    }

    const preview = await getAttachmentObjectUrl(props.attachment.id);
    if (version !== loadVersion) {
      URL.revokeObjectURL(preview.url);
      return;
    }
    if (preview.contentType.startsWith("image/") || looksLikeImage(props.attachment.original_filename)) {
      previewUrl.value = preview.url;
      ownedUrl = preview.url;
      return;
    }
    if (preview.contentType === "application/pdf" || looksLikePdf(props.attachment.original_filename)) {
      ownedUrl = preview.url;
      await renderPdf(preview.url, version);
      return;
    }
    URL.revokeObjectURL(preview.url);
  } catch {
    if (version === loadVersion) failed.value = true;
  }
}

watch(
  () => props.attachment.id,
  () => {
    void loadPreview();
  },
  { immediate: true }
);

onBeforeUnmount(resetPreview);
</script>

<template>
  <div
    class="grid shrink-0 place-items-center overflow-hidden bg-slate-100"
    :class="large ? 'h-full min-h-24 w-full rounded-none' : 'h-11 w-11 rounded-md'"
  >
    <img
      v-if="previewUrl && !failed"
      :src="previewUrl"
      :alt="attachment.original_filename"
      class="h-full w-full object-cover"
    />
    <canvas
      v-else-if="pdfPreview && !failed"
      ref="pdfCanvas"
      class="max-h-full max-w-full bg-white"
      :aria-label="`${attachment.original_filename} 首页缩略图`"
    />
    <FileImage v-else :class="large ? 'h-8 w-8 text-slate-400' : 'h-4 w-4 text-slate-400'" />
  </div>
</template>
