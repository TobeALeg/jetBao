<script setup lang="ts">
import { ref } from "vue";

defineProps<{
  modelValue: boolean;
  label: string;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
}>();

const initialized = ref(false);

function toggle(currentValue: boolean) {
  initialized.value = true;
  emit("update:modelValue", !currentValue);
}
</script>

<template>
  <button
    class="status-toggle"
    type="button"
    role="switch"
    :aria-checked="modelValue"
    :aria-label="label"
    @click="toggle(modelValue)"
  >
    <span class="t-toggle" :class="{ 'is-init': initialized }" :data-on="modelValue" aria-hidden="true">
      <span class="t-toggle-thumb"></span>
    </span>
    <span>{{ modelValue ? "启用" : "停用" }}</span>
  </button>
</template>

<style scoped>
.status-toggle {
  display: inline-flex;
  min-height: 2.25rem;
  align-items: center;
  gap: 0.5rem;
  border-radius: 0.375rem;
  padding: 0 0.375rem;
  color: #475569;
  font-size: 0.875rem;
}

.status-toggle:focus-visible {
  border-radius: 0.375rem;
  outline: 2px solid var(--accent-ink, #2f6f68);
  outline-offset: 2px;
}

.status-toggle.is-modified {
  background: var(--accent-soft, #eef5f4);
  color: var(--accent-ink, #2f6f68);
}

.t-toggle {
  position: relative;
  display: inline-flex;
  width: 2.25rem;
  height: 1.25rem;
  flex: none;
  align-items: center;
  border-radius: 9999px;
  background: #cbd5e1;
  padding: 0.125rem;
  transition: background var(--toggle-track) var(--toggle-ease);
}

.t-toggle[data-on="true"] {
  background: var(--accent, #34756d);
}

.t-toggle-thumb {
  display: block;
  width: 1rem;
  height: 1rem;
  border-radius: 9999px;
  background: white;
  box-shadow: 0 1px 2px rgb(15 23 42 / 0.25);
  translate: 0 0;
  will-change: translate;
}
.t-toggle[data-on="true"] .t-toggle-thumb { translate: var(--toggle-travel) 0; }
.t-toggle.is-init[data-on="true"] .t-toggle-thumb { animation: t-toggle-on var(--toggle-dur) var(--toggle-ease) both; }
.t-toggle.is-init[data-on="false"] .t-toggle-thumb { animation: t-toggle-off var(--toggle-dur) var(--toggle-ease) both; }
@keyframes t-toggle-on {
  0% { translate: 0 0; }
  55% { translate: calc(var(--toggle-travel) + var(--toggle-ov1)) 0; }
  80% { translate: calc(var(--toggle-travel) - var(--toggle-ov2)) 0; }
  100% { translate: var(--toggle-travel) 0; }
}
@keyframes t-toggle-off {
  0% { translate: var(--toggle-travel) 0; }
  55% { translate: calc(0px - var(--toggle-ov1)) 0; }
  80% { translate: var(--toggle-ov2) 0; }
  100% { translate: 0 0; }
}

@media (prefers-reduced-motion: reduce) {
  .t-toggle-thumb { animation: none !important; }
}
</style>
