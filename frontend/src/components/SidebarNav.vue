<script setup lang="ts">
import { BookOpen, Home, ReceiptText, Settings, ShieldCheck } from "lucide-vue-next";
import { computed } from "vue";
import type { Component } from "vue";
import type { User, ViewKey } from "../types";

const props = defineProps<{
  user: User;
  currentView: ViewKey;
  draftCount: number;
  pendingOcrCount: number;
}>();

defineEmits<{
  "change-view": [view: ViewKey];
}>();

interface NavItem {
  key: ViewKey;
  label: string;
  icon: Component;
  adminOnly?: boolean;
}

const navItems: NavItem[] = [
  { key: "monthly", label: "个人报销", icon: Home },
  { key: "history", label: "报销记录总览", icon: ReceiptText, adminOnly: true },
  { key: "admin-users", label: "管理", icon: ShieldCheck, adminOnly: true },
  { key: "guide", label: "使用指南", icon: BookOpen },
  { key: "settings", label: "个人设置", icon: Settings },
];

const visibleNavItems = computed(() =>
  navItems.filter((item) => !item.adminOnly || props.user.role === "admin")
);

function badgeFor(key: ViewKey): number {
  if (key === "monthly") return props.draftCount + props.pendingOcrCount;
  return 0;
}

function isActive(key: ViewKey): boolean {
  return props.currentView === key;
}
</script>

<template>
  <aside class="border-b border-slate-200 bg-white lg:min-h-screen lg:w-60 lg:border-b-0 lg:border-r">
    <div class="flex h-16 items-center border-b border-slate-200 px-5">
      <div>
        <div class="text-base font-semibold tracking-normal text-ink">JetBao</div>
        <div class="text-xs text-slate-500">内部报销整理</div>
      </div>
    </div>

    <nav class="flex gap-1 overflow-x-auto px-3 py-4 lg:flex-col lg:overflow-visible">
      <button
        v-for="item in visibleNavItems"
        :key="item.key"
        class="nav-item shrink-0 lg:w-full"
        :class="isActive(item.key) ? 'nav-item-active' : 'nav-item-idle'"
        type="button"
        @click="$emit('change-view', item.key)"
      >
        <span class="nav-item-icon">
          <component :is="item.icon" class="h-4 w-4" />
        </span>
        <span class="nav-item-label">{{ item.label }}</span>
        <span v-if="badgeFor(item.key)" class="nav-badge">{{ badgeFor(item.key) }}</span>
      </button>
    </nav>
  </aside>
</template>
