<script setup lang="ts">
import { Download, FilePlus2, ReceiptText, ShieldCheck, Users } from "lucide-vue-next";
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
  { key: "my-expenses", label: "我的报销", icon: ReceiptText },
  { key: "new-expense", label: "报销整理", icon: FilePlus2 },
  { key: "admin-ledger", label: "管理后台", icon: ShieldCheck, adminOnly: true },
  { key: "admin-users", label: "员工管理", icon: Users, adminOnly: true },
  { key: "export", label: "导出", icon: Download, adminOnly: true }
];

function visible(item: NavItem) {
  return !item.adminOnly || props.user.role === "admin";
}

function badgeFor(key: ViewKey): number {
  if (key === "my-expenses") return props.draftCount;
  if (key === "new-expense") return props.draftCount + props.pendingOcrCount;
  return 0;
}
</script>

<template>
  <aside class="border-b border-slate-200 bg-white lg:min-h-screen lg:w-56 lg:border-b-0 lg:border-r">
    <div class="flex h-16 items-center border-b border-slate-200 px-5">
      <div>
        <div class="text-base font-semibold tracking-normal text-ink">JetBao</div>
        <div class="text-xs text-slate-500">内部报销整理</div>
      </div>
    </div>
    <nav class="flex gap-1 overflow-x-auto px-3 py-3 lg:flex-col lg:overflow-visible">
      <button
        v-for="item in navItems.filter(visible)"
        :key="item.key"
        class="inline-flex h-10 shrink-0 items-center gap-3 rounded-md px-3 text-sm transition lg:w-full"
        :class="
          currentView === item.key
            ? 'bg-teal-50 text-teal-800'
            : 'text-slate-600 hover:bg-slate-50 hover:text-slate-950'
        "
        type="button"
        @click="$emit('change-view', item.key)"
      >
        <component :is="item.icon" class="h-4 w-4" />
        <span>{{ item.label }}</span>
        <span v-if="badgeFor(item.key)" class="nav-badge">{{ badgeFor(item.key) }}</span>
      </button>
    </nav>
  </aside>
</template>
