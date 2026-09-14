<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from "vue";
import { Check, ChevronDown } from "lucide-vue-next";

interface SelectOption {
  label: string;
  value: string;
}

const props = defineProps<{
  modelValue: string;
  options: SelectOption[];
  label: string;
  placeholder?: string;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: string];
}>();

const open = ref(false);
const root = ref<HTMLElement | null>(null);
const trigger = ref<HTMLButtonElement | null>(null);
const floatingPanel = ref<HTMLElement | null>(null);
const panelPosition = ref({ top: 0, left: 0, minWidth: 0, maxWidth: 0 });
const hasSelection = computed(() => props.options.some((option) => option.value === props.modelValue));
const selectedLabel = computed(
  () => props.options.find((option) => option.value === props.modelValue)?.label || props.modelValue || props.placeholder || "请选择"
);

function updatePanelPosition() {
  const rect = trigger.value?.getBoundingClientRect();
  if (!rect) return;
  panelPosition.value = {
    top: rect.bottom + 4,
    left: Math.max(16, Math.min(rect.left, window.innerWidth - 336)),
    minWidth: rect.width,
    maxWidth: window.innerWidth - 32
  };
}

async function toggleOpen() {
  if (open.value) {
    open.value = false;
    return;
  }
  updatePanelPosition();
  open.value = true;
  await nextTick();
  updatePanelPosition();
}

function choose(value: string) {
  emit("update:modelValue", value);
  open.value = false;
}

function handleOutsidePointer(event: PointerEvent) {
  const target = event.target as Node;
  if (root.value?.contains(target) || floatingPanel.value?.contains(target)) return;
  open.value = false;
}

function closeAndReposition() {
  if (!open.value) return;
  updatePanelPosition();
}

onMounted(() => {
  document.addEventListener("pointerdown", handleOutsidePointer);
  window.addEventListener("resize", closeAndReposition);
  window.addEventListener("scroll", closeAndReposition, true);
});

onUnmounted(() => {
  document.removeEventListener("pointerdown", handleOutsidePointer);
  window.removeEventListener("resize", closeAndReposition);
  window.removeEventListener("scroll", closeAndReposition, true);
});
</script>

<template>
  <div ref="root" class="t-acc" :data-open="open">
    <button
      ref="trigger"
      class="t-acc-head"
      type="button"
      :aria-expanded="open"
      :aria-label="label"
      @click="toggleOpen"
      @keydown.esc="open = false"
    >
      <span class="selected-label truncate" :class="{ 'is-placeholder': !hasSelection }">{{ selectedLabel }}</span>
      <span class="t-acc-chevron" aria-hidden="true">
        <ChevronDown class="h-4 w-4" />
      </span>
    </button>
    <Teleport to="body">
      <div
        ref="floatingPanel"
        class="t-acc-panel t-acc-floating"
        :data-open="open"
        :aria-hidden="!open"
        :style="{
          top: `${panelPosition.top}px`,
          left: `${panelPosition.left}px`,
          minWidth: `${panelPosition.minWidth}px`,
          maxWidth: `${panelPosition.maxWidth}px`
        }"
      >
        <div class="t-acc-panel-inner">
          <div class="option-list" role="listbox" :aria-label="label">
            <button
              v-for="option in options"
              :key="option.value"
              class="option-button"
              type="button"
              role="option"
              :aria-selected="option.value === modelValue"
              :tabindex="open ? 0 : -1"
              @click="choose(option.value)"
            >
              <span class="whitespace-nowrap">{{ option.label }}</span>
              <Check v-if="option.value === modelValue" class="h-3.5 w-3.5 shrink-0 text-teal-700" />
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.t-acc {
  width: 100%;
}

.t-acc-head {
  display: flex;
  min-height: 2.25rem;
  width: 100%;
  align-items: center;
  justify-content: space-between;
  gap: 0.375rem;
  border-radius: 0.375rem;
  padding: 0 0.25rem;
  color: #334155;
  font-size: 0.875rem;
  line-height: 1.25rem;
  text-align: left;
  transition: background-color 150ms ease-out;
}

.t-acc-head:hover,
.t-acc-head:focus-visible {
  background: #f8fafc;
  outline: none;
}

.t-acc.is-create-field .selected-label.is-placeholder {
  color: #94a3b8;
  font-size: 0.75rem;
}

.t-acc.is-modified .t-acc-head {
  background: #ecfdf5;
  color: #115e59;
}

/* Transitions.dev accordion: animate intrinsic height without measuring it. */
.t-acc-panel {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows var(--acc-collapse) var(--acc-ease);
}
.t-acc-panel[data-open="true"] {
  grid-template-rows: 1fr;
  transition: grid-template-rows var(--acc-expand) var(--acc-ease);
}
.t-acc-panel-inner {
  overflow: hidden;
  opacity: 0;
  filter: blur(2px);
  transition:
    opacity var(--acc-collapse) var(--acc-ease),
    filter var(--acc-collapse) var(--acc-ease);
}
.t-acc-panel[data-open="true"] .t-acc-panel-inner {
  opacity: 1;
  filter: blur(0);
  transition:
    opacity var(--acc-expand) var(--acc-ease),
    filter var(--acc-expand) var(--acc-ease);
}

.t-acc-floating {
  position: fixed;
  z-index: 60;
  width: max-content;
  overflow: hidden;
  border-radius: 0.5rem;
  background: white;
  box-shadow: 0 12px 30px rgb(15 23 42 / 0.14), 0 2px 6px rgb(15 23 42 / 0.08);
  pointer-events: none;
}

.t-acc-floating[data-open="true"] {
  pointer-events: auto;
}
.t-acc-chevron {
  display: inline-flex;
  flex: none;
  transform: scaleY(1);
  transform-origin: center;
  transition: transform var(--acc-chevron) var(--acc-ease);
}
.t-acc-chevron :deep(path) {
  vector-effect: non-scaling-stroke;
}
.t-acc[data-open="true"] .t-acc-chevron {
  transform: scaleY(-1);
}

.option-list {
  padding: 0.25rem;
}

.option-button {
  display: flex;
  width: 100%;
  align-items: center;
  justify-content: space-between;
  gap: 0.375rem;
  border-radius: 0.25rem;
  padding: 0.5rem 0.625rem;
  color: #475569;
  font-size: 0.875rem;
  line-height: 1.25rem;
  text-align: left;
  transition: background-color 150ms ease-out, color 150ms ease-out;
}

.option-button:hover,
.option-button:focus-visible,
.option-button[aria-selected="true"] {
  background: #f1f5f9;
  color: #0f172a;
  outline: none;
}

@media (prefers-reduced-motion: reduce) {
  .t-acc-panel, .t-acc-panel-inner, .t-acc-chevron {
    transition: none !important;
  }
}
</style>
