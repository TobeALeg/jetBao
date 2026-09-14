<script setup lang="ts">
import { HelpCircle, LogOut } from "lucide-vue-next";
import UserMenu from "./UserMenu.vue";
import type { User } from "../types";

defineProps<{
  user: User;
}>();

defineEmits<{
  logout: [];
  "open-guide": [];
}>();
</script>

<template>
  <header class="flex h-16 items-center justify-between border-b border-hairline bg-white px-4 sm:px-6 lg:px-8">
    <div class="min-w-0">
      <div class="truncate text-sm font-medium text-slate-900">{{ user.company_entity }}</div>
      <div class="text-xs text-slate-500">{{ user.role === "admin" ? "管理员" : "员工" }}</div>
    </div>

    <div class="flex items-center gap-1.5">
      <!-- 指南：无框线图标按钮，鼠标悬停才显底 -->
      <button
        class="grid h-control-sm w-control-sm place-items-center rounded-control text-slate-500 transition duration-1 ease-standard hover:bg-surface-soft hover:text-slate-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        type="button"
        aria-label="打开使用指南"
        title="使用指南"
        @click="$emit('open-guide')"
      >
        <HelpCircle class="h-4 w-4" />
      </button>

      <UserMenu :user="user" />

      <button class="secondary-button gap-2 px-3" type="button" @click="$emit('logout')">
        <LogOut class="h-4 w-4" />
        <span class="hidden sm:inline">退出</span>
      </button>
    </div>
  </header>
</template>
