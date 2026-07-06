<script setup lang="ts">
defineProps<{
  stats: Array<{
    label: string;
    value: string;
    tone?: "default" | "warning" | "danger";
  }>;
}>();
</script>

<template>
  <div class="tool-panel grid divide-y divide-slate-200 rounded-lg sm:grid-cols-2 sm:divide-x sm:divide-y-0 lg:grid-cols-4">
    <div v-for="item in stats" :key="item.label" class="px-5 py-4">
      <div class="text-xs text-slate-500">{{ item.label }}</div>
      <div
        class="mt-1 text-2xl font-semibold tracking-normal"
        :class="{
          'text-ink': !item.tone || item.tone === 'default',
          'text-amber-700': item.tone === 'warning',
          'text-rose-700': item.tone === 'danger'
        }"
      >
        {{ item.value }}
      </div>
    </div>
  </div>
</template>
