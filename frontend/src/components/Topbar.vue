<script setup lang="ts">
import { LogOut } from "lucide-vue-next";
import type { User } from "../types";

defineProps<{
  user: User;
}>();

defineEmits<{
  logout: [];
}>();
</script>

<template>
  <header class="flex h-16 items-center justify-between border-b border-slate-200 bg-white px-4 sm:px-6 lg:px-8">
    <div class="min-w-0">
      <div class="truncate text-sm font-medium text-ink">{{ user.company_entity }}</div>
      <div class="text-xs text-slate-500">{{ user.role === "admin" ? "管理员" : "员工" }}</div>
    </div>
    <div class="flex items-center gap-3">
      <div class="hidden text-right sm:block">
        <div class="text-sm font-medium text-slate-800">{{ user.employee_name }}</div>
        <div class="text-xs text-slate-500">@{{ user.username }}</div>
      </div>
      <button class="secondary-button h-9 px-3" type="button" @click="$emit('logout')">
        <LogOut class="h-4 w-4" />
        <span class="hidden sm:inline">退出</span>
      </button>
    </div>
  </header>
</template>
