<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import AppShell from "./components/AppShell.vue";
import LoginView from "./views/LoginView.vue";
import MonthlyView from "./views/MonthlyView.vue";
import PendingMaterialsView from "./views/PendingMaterialsView.vue";
import HistoryView from "./views/HistoryView.vue";
import AdminUsersView from "./views/AdminUsersView.vue";
import { clearToken, getMe, getToken, listExpenses } from "./services/api";
import type { Expense, User, ViewKey, WorkspaceMode } from "./types";

const user = ref<User | null>(null);
const currentView = ref<ViewKey>("monthly");
const loadingSession = ref(true);
const refreshKey = ref(0);
const allExpenses = ref<Expense[]>([]);

const draftCount = computed(() => allExpenses.value.filter((e) => e.status === "pending").length);
const pendingOcrCount = computed(() =>
  allExpenses.value.reduce((sum, e) => sum + e.attachments.filter((f) => f.ocr_status !== "success").length, 0)
);
const adminViews = new Set<ViewKey>(["history", "admin-users"]);
const workspaceMode = computed<WorkspaceMode>(() =>
  user.value?.role === "admin" && adminViews.has(currentView.value) ? "admin" : "personal"
);

async function loadExpenses() {
  if (!user.value) return;
  try {
    allExpenses.value = await listExpenses();
  } catch {
    // non-critical
  }
}

async function restoreSession() {
  if (!getToken()) {
    loadingSession.value = false;
    return;
  }
  try {
    user.value = await getMe();
    await loadExpenses();
  } catch {
    clearToken();
  } finally {
    loadingSession.value = false;
  }
}

function handleLogin(nextUser: User) {
  user.value = nextUser;
  currentView.value = "monthly";
  loadExpenses();
}

function handleLogout() {
  clearToken();
  user.value = null;
  currentView.value = "monthly";
  allExpenses.value = [];
}

function handleChangeView(view: ViewKey) {
  if (adminViews.has(view) && user.value?.role !== "admin") return;
  currentView.value = view;
}

function handleChangeWorkspaceMode(mode: WorkspaceMode) {
  if (mode === "admin" && user.value?.role !== "admin") return;
  currentView.value = mode === "admin" ? "history" : "monthly";
}

onMounted(restoreSession);
watch(refreshKey, loadExpenses);
watch(() => currentView.value, (v) => {
  if (v === "monthly" || v === "materials") refreshKey.value += 1;
});
</script>

<template>
  <div v-if="loadingSession" class="grid min-h-screen place-items-center bg-stone-50 text-sm text-slate-500">
    正在进入系统...
  </div>

  <LoginView v-else-if="!user" @login-success="handleLogin" />

  <AppShell
    v-else
    :user="user"
    :current-view="currentView"
    :workspace-mode="workspaceMode"
    :draft-count="draftCount"
    :pending-ocr-count="pendingOcrCount"
    @change-view="handleChangeView"
    @change-workspace-mode="handleChangeWorkspaceMode"
    @logout="handleLogout"
  >
    <MonthlyView
      v-show="currentView === 'monthly'"
      :user="user"
      :refresh-key="refreshKey"
      @refreshed="loadExpenses()"
      @open-materials="currentView = 'materials'"
    />
    <PendingMaterialsView
      v-show="currentView === 'materials'"
      :user="user"
      :refresh-key="refreshKey"
      @refreshed="loadExpenses()"
    />
    <HistoryView
      v-show="currentView === 'history'"
      :user="user"
      :refresh-key="refreshKey"
    />
    <AdminUsersView v-if="currentView === 'admin-users' && user.role === 'admin'" />
  </AppShell>
</template>
