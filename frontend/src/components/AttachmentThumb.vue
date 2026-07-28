<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import { FileImage } from "lucide-vue-next";
import { getAttachmentObjectUrl } from "../services/api";
import { looksLikeImage } from "../utils/attachmentUtils";
import type { Attachment } from "../types";

const props = defineProps<{
  attachment: Attachment;
  large?: boolean;
}>();

const previewUrl = ref(props.attachment.preview_url ?? "");
const failed = ref(false);
let ownedUrl = "";

async function loadPreview() {
  if (previewUrl.value) return;
  try {
    const preview = await getAttachmentObjectUrl(props.attachment.id);
    if (preview.contentType.startsWith("image/") || looksLikeImage(props.attachment.original_filename)) {
      previewUrl.value = preview.url;
      ownedUrl = preview.url;
      return;
    }
    URL.revokeObjectURL(preview.url);
  } catch {
    failed.value = true;
  }
}

watch(
  () => props.attachment.id,
  () => {
    if (ownedUrl) {
      URL.revokeObjectURL(ownedUrl);
      ownedUrl = "";
    }
    previewUrl.value = props.attachment.preview_url ?? "";
    failed.value = false;
    void loadPreview();
  },
  { immediate: true }
);

onBeforeUnmount(() => {
  if (ownedUrl) URL.revokeObjectURL(ownedUrl);
});
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
    <FileImage v-else :class="large ? 'h-8 w-8 text-slate-400' : 'h-4 w-4 text-slate-400'" />
  </div>
</template>
