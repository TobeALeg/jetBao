<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from "vue";
import { X } from "lucide-vue-next";
import GuideView from "../views/GuideView.vue";
import type { User } from "../types";

const props = defineProps<{
  open: boolean;
  user: User;
}>();

const emit = defineEmits<{
  close: [];
}>();

const panel = ref<HTMLElement | null>(null);

function onKeydown(event: KeyboardEvent) {
  if (event.key === "Escape") emit("close");
}

watch(
  () => props.open,
  (open) => {
    // 打开时锁住页面滚动，关闭时恢复
    document.body.style.overflow = open ? "hidden" : "";
    if (open) {
      window.addEventListener("keydown", onKeydown);
    } else {
      window.removeEventListener("keydown", onKeydown);
    }
  }
);

onBeforeUnmount(() => {
  document.body.style.overflow = "";
  window.removeEventListener("keydown", onKeydown);
});
</script>

<template>
  <Teleport to="body">
    <Transition name="drawer">
      <div
        v-if="open"
        class="fixed inset-0 z-[70] flex justify-end bg-slate-900/40"
        @click.self="emit('close')"
      >
        <section
          ref="panel"
          class="relative flex h-full w-full max-w-4xl flex-col overflow-hidden bg-surface-canvas shadow-overlay"
          role="dialog"
          aria-modal="true"
          aria-label="使用指南"
        >
          <button
            class="absolute right-4 top-4 z-10 inline-flex h-8 w-8 items-center justify-center rounded-control text-slate-500 transition duration-1 ease-standard hover:bg-surface-mute hover:text-slate-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            type="button"
            aria-label="关闭使用指南"
            @click="emit('close')"
          >
            <X class="h-4 w-4" />
          </button>

          <div class="min-h-0 flex-1 overflow-y-auto">
            <GuideView :user="user" variant="drawer" />
          </div>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
/* 从右侧滑出：只动 transform / opacity，不动布局属性 */
.drawer-enter-active,
.drawer-leave-active {
  transition: opacity var(--dur-3) var(--ease-standard);
}

.drawer-enter-active section,
.drawer-leave-active section {
  transition: transform var(--dur-3) var(--ease-standard);
}

.drawer-enter-from,
.drawer-leave-to {
  opacity: 0;
}

.drawer-enter-from section,
.drawer-leave-to section {
  transform: translateX(100%);
}

@media (prefers-reduced-motion: reduce) {
  .drawer-enter-active,
  .drawer-leave-active,
  .drawer-enter-active section,
  .drawer-leave-active section {
    transition: none !important;
  }
}
</style>
