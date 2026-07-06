<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";
import { FileImage } from "lucide-vue-next";
import { getAttachmentObjectUrl } from "../services/api";
import type { Attachment } from "../types";

const props = defineProps<{
  attachment: Attachment;
}>();

const previewUrl = ref(props.attachment.preview_url ?? "");
const failed = ref(false);
let ownedUrl = "";

function looksLikeImage(filename: string): boolean {
  return /\.(png|jpe?g|webp|gif|bmp)$/i.test(filename);
}

onMounted(async () => {
  if (previewUrl.value || !looksLikeImage(props.attachment.original_filename)) return;
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
});

onBeforeUnmount(() => {
  if (ownedUrl) URL.revokeObjectURL(ownedUrl);
});
</script>

<template>
  <div class="grid h-11 w-11 shrink-0 place-items-center overflow-hidden rounded-md bg-slate-100">
    <img
      v-if="previewUrl && !failed"
      :src="previewUrl"
      :alt="attachment.original_filename"
      class="h-full w-full object-cover"
    />
    <FileImage v-else class="h-4 w-4 text-slate-400" />
  </div>
</template>
