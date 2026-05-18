<script setup lang="ts">
import SidebarNav from "./SidebarNav.vue";
import Topbar from "./Topbar.vue";
import type { User, ViewKey } from "../types";

defineProps<{
  user: User;
  currentView: ViewKey;
}>();

defineEmits<{
  "change-view": [view: ViewKey];
  logout: [];
}>();
</script>

<template>
  <div class="min-h-screen bg-stone-50 text-ink">
    <div class="flex min-h-screen flex-col lg:flex-row">
      <SidebarNav :user="user" :current-view="currentView" @change-view="$emit('change-view', $event)" />
      <div class="flex min-w-0 flex-1 flex-col">
        <Topbar :user="user" @logout="$emit('logout')" />
        <main class="min-w-0 flex-1 px-4 py-5 sm:px-6 lg:px-8">
          <slot />
        </main>
      </div>
    </div>
  </div>
</template>

