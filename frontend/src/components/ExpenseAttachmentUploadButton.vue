<script setup lang="ts">
import { ref } from "vue";
import { ImagePlus, Loader2 } from "lucide-vue-next";
import { linkExpenseAttachments, uploadAttachments } from "../services/api";
import type { Expense } from "../types";

const props = withDefaults(
  defineProps<{
    expense: Expense;
    disabled?: boolean;
    compact?: boolean;
    label?: string;
  }>(),
  {
    disabled: false,
    compact: false,
    label: "上传附件"
  }
);

const emit = defineEmits<{
  uploaded: [expense: Expense];
  error: [message: string];
}>();

const inputRef = ref<HTMLInputElement | null>(null);
const uploading = ref(false);

function isTransactionFile(file: File): boolean {
  return file.type.startsWith("image/") || /\.(png|jpe?g|webp|gif|bmp)$/i.test(file.name);
}

async function handleFiles(event: Event) {
  const input = event.target as HTMLInputElement;
  const files = Array.from(input.files ?? []).filter(isTransactionFile);
  input.value = "";

  if (!files.length) {
    emit("error", "请上传交易记录图片。");
    return;
  }

  uploading.value = true;
  try {
    const attachments = await uploadAttachments(files);
    const updated = await linkExpenseAttachments(props.expense.id, {
      attachment_ids: attachments.map((item) => item.id)
    });
    emit("uploaded", updated);
  } catch (err) {
    emit("error", err instanceof Error ? err.message : "附件上传失败");
  } finally {
    uploading.value = false;
  }
}
</script>

<template>
  <span class="inline-flex">
    <input ref="inputRef" class="hidden" type="file" accept="image/*" multiple @change="handleFiles" />
    <button
      class="secondary-button"
      :class="compact ? 'h-8 px-2 text-xs' : 'h-9 px-3'"
      type="button"
      :disabled="disabled || uploading"
      @click="inputRef?.click()"
    >
      <Loader2 v-if="uploading" class="h-4 w-4 animate-spin" />
      <ImagePlus v-else class="h-4 w-4" />
      {{ uploading ? "上传中" : label }}
    </button>
  </span>
</template>
