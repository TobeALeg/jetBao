<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import AppShell from "./components/AppShell.vue";
import GuideWelcomeModal from "./components/GuideWelcomeModal.vue";
import LoginView from "./views/LoginView.vue";
import MonthlyView from "./views/MonthlyView.vue";
import HistoryView from "./views/HistoryView.vue";
import SettingsView from "./views/SettingsView.vue";
import GuideView from "./views/GuideView.vue";
import AdminUsersView from "./views/AdminUsersView.vue";
import { clearToken, getMe, listExpenses, logout, markGuideSeen } from "./services/api";
import type { Expense, User, ViewKey } from "./types";

const ADMIN_ONLY_VIEWS: ViewKey[] = ["admin-users"];

const user = ref<User | null>(null);
const currentView = ref<ViewKey>("monthly");
const loadingSession = ref(true);
const refreshKey = ref(0);
const allExpenses = ref<Expense[]>([]);
const showGuideWelcome = ref(false);

const draftCount = computed(() => allExpenses.value.filter((e) => e.status === "pending").length);
const pendingOcrCount = computed(() =>
  allExpenses.value.reduce(
    (sum, e) => sum + e.attachments.filter((f) => f.ocr_status !== "success" && f.ocr_status !== "skipped").length,
    0
  )
);

async function loadExpenses() {
  if (!user.value) return;
  try {
    allExpenses.value = await listExpenses();
  } catch {
    // non-critical
  }
}

function maybeShowGuideWelcome() {
  showGuideWelcome.value = Boolean(user.value && !user.value.guide_seen);
}

async function dismissGuideWelcome(openFullGuide = false) {
  if (!user.value || user.value.guide_seen) {
    showGuideWelcome.value = false;
    if (openFullGuide) currentView.value = "guide";
    return;
  }
  try {
    user.value = await markGuideSeen();
  } catch {
    user.value = { ...user.value, guide_seen: true };
  }
  showGuideWelcome.value = false;
  if (openFullGuide) currentView.value = "guide";
}

function ensureAllowedView() {
  if (user.value?.role !== "admin" && ADMIN_ONLY_VIEWS.includes(currentView.value)) {
    currentView.value = "monthly";
  }
}

async function restoreSession() {
  try {
    user.value = await getMe();
    ensureAllowedView();
    await loadExpenses();
    maybeShowGuideWelcome();
  } catch {
    clearToken();
  } finally {
    loadingSession.value = false;
  }
}

function handleLogin(nextUser: User) {
  user.value = nextUser;
  currentView.value = "monthly";
  ensureAllowedView();
  loadExpenses();
  maybeShowGuideWelcome();
}

async function handleLogout() {
  try {
    const result = await logout();
    clearToken();
    window.location.assign(result.logout_url);
    return;
  } catch {
    // Even if central logout is unavailable, clear the local UI state.
  }
  clearToken();
  user.value = null;
  currentView.value = "monthly";
  allExpenses.value = [];
  showGuideWelcome.value = false;
}

function handleChangeView(view: ViewKey) {
  if (ADMIN_ONLY_VIEWS.includes(view) && user.value?.role !== "admin") return;
  currentView.value = view;
}

onMounted(restoreSession);
watch(refreshKey, loadExpenses);
watch(
  () => currentView.value,
  (view) => {
    if (view === "monthly" || view === "history") refreshKey.value += 1;
  }
);
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
    :draft-count="draftCount"
    :pending-ocr-count="pendingOcrCount"
    @change-view="handleChangeView"
    @logout="handleLogout"
  >
    <GuideWelcomeModal
      :open="showGuideWelcome"
      :user="user"
      @dismiss="dismissGuideWelcome(false)"
      @view-full-guide="dismissGuideWelcome(true)"
    />
    <MonthlyView
      v-show="currentView === 'monthly'"
      :user="user"
      :refresh-key="refreshKey"
      @refreshed="loadExpenses()"
    />
    <HistoryView
      v-show="currentView === 'history'"
      :user="user"
      :refresh-key="refreshKey"
      @expenses-changed="refreshKey += 1"
    />
    <SettingsView v-show="currentView === 'settings'" :user="user" />
    <GuideView v-show="currentView === 'guide'" :user="user" />
    <AdminUsersView v-show="currentView === 'admin-users'" v-if="user.role === 'admin'" />
  </AppShell>
</template>
