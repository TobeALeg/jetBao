<script setup lang="ts">
import { Download, FilePlus2, ReceiptText, ShieldCheck, UserRound, Users } from "lucide-vue-next";
import { computed } from "vue";
import type { Component } from "vue";
import type { User, ViewKey, WorkspaceMode } from "../types";

const props = defineProps<{
  user: User;
  currentView: ViewKey;
  workspaceMode: WorkspaceMode;
  draftCount: number;
  pendingOcrCount: number;
}>();

defineEmits<{
  "change-view": [view: ViewKey];
  "change-workspace-mode": [mode: WorkspaceMode];
}>();

interface NavItem {
  key: ViewKey;
  label: string;
  icon: Component;
}

const personalNavItems: NavItem[] = [
  { key: "my-expenses", label: "我的报销", icon: ReceiptText },
  { key: "new-expense", label: "报销整理", icon: FilePlus2 }
];

const adminNavItems: NavItem[] = [
  { key: "admin-ledger", label: "管理后台", icon: ShieldCheck },
  { key: "admin-users", label: "员工管理", icon: Users },
  { key: "export", label: "导出", icon: Download }
];

const navItems = computed(() => (props.workspaceMode === "admin" ? adminNavItems : personalNavItems));

function badgeFor(key: ViewKey): number {
  if (key === "my-expenses") return props.draftCount;
  if (key === "new-expense") return props.draftCount + props.pendingOcrCount;
  return 0;
}

function modeClass(mode: WorkspaceMode): string {
  return props.workspaceMode === mode
    ? "bg-white text-teal-800 shadow-sm"
    : "text-slate-500 hover:text-slate-800";
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
    <div v-if="user.role === 'admin'" class="border-b border-slate-200 px-3 py-3">
      <div class="grid grid-cols-2 rounded-md bg-slate-100 p-1">
        <button
          class="inline-flex h-9 items-center justify-center gap-2 rounded px-2 text-sm font-medium transition"
          :class="modeClass('personal')"
          type="button"
          @click="$emit('change-workspace-mode', 'personal')"
        >
          <UserRound class="h-4 w-4" />
          个人
        </button>
        <button
          class="inline-flex h-9 items-center justify-center gap-2 rounded px-2 text-sm font-medium transition"
          :class="modeClass('admin')"
          type="button"
          @click="$emit('change-workspace-mode', 'admin')"
        >
          <ShieldCheck class="h-4 w-4" />
          管理
        </button>
      </div>
    </div>
    <nav class="flex gap-1 overflow-x-auto px-3 py-3 lg:flex-col lg:overflow-visible">
      <button
        v-for="item in navItems"
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
