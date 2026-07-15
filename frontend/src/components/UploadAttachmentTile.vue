<script setup lang="ts">
import { Loader2, Trash2 } from "lucide-vue-next";
import AttachmentThumb from "./AttachmentThumb.vue";
import { looksLikePdf } from "../utils/attachmentUtils";
import type { Attachment } from "../types";

defineProps<{
  attachment: Attachment;
  removable?: boolean;
  removing?: boolean;
}>();

const emit = defineEmits<{
  preview: [attachment: Attachment];
  remove: [attachment: Attachment];
}>();
</script>

<template>
  <div class="group relative overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
    <button
      class="block aspect-square w-full overflow-hidden transition hover:ring-2 hover:ring-teal-600/40"
      type="button"
      @click="emit('preview', attachment)"
    >
      <AttachmentThumb :attachment="attachment" large />
      <span
        v-if="looksLikePdf(attachment.original_filename)"
        class="absolute bottom-0 left-0 right-0 bg-slate-900/60 px-1 py-0.5 text-[10px] text-white"
      >
        PDF
      </span>
    </button>

    <button
      v-if="removable"
      class="absolute right-2 top-2 z-20 inline-flex h-8 min-w-8 items-center justify-center gap-1 rounded-full border border-rose-200 bg-rose-600 px-2 text-white shadow-md transition hover:bg-rose-700 disabled:cursor-not-allowed disabled:opacity-60"
      :disabled="removing"
      type="button"
      aria-label="删除"
      @click.stop="emit('remove', attachment)"
    >
      <Loader2 v-if="removing" class="h-3.5 w-3.5 animate-spin" />
      <Trash2 v-else class="h-3.5 w-3.5" />
      <span class="text-[11px] font-medium leading-none">删除</span>
    </button>

    <p class="truncate border-t border-slate-100 px-2 py-1.5 text-[11px] text-slate-600" :title="attachment.original_filename">
      {{ attachment.original_filename }}
    </p>
  </div>
</template>
