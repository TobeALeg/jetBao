<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import AppShell from "./components/AppShell.vue";
import LoginView from "./views/LoginView.vue";
import MyExpensesView from "./views/MyExpensesView.vue";
import NewExpenseView from "./views/NewExpenseView.vue";
import AdminLedgerView from "./views/AdminLedgerView.vue";
import AdminUsersView from "./views/AdminUsersView.vue";
import ExportView from "./views/ExportView.vue";
import { clearToken, getMe, getToken, listExpenses } from "./services/api";
import type { Expense, User, ViewKey } from "./types";

const user = ref<User | null>(null);
const currentView = ref<ViewKey>("my-expenses");
const loadingSession = ref(true);
const refreshKey = ref(0);
const draftToComplete = ref<Expense | null>(null);
const adminLedgerStatus = ref<string | null>(null);
const allExpenses = ref<Expense[]>([]);

const draftCount = computed(() => allExpenses.value.filter((e) => e.status === "draft").length);
const pendingOcrCount = computed(() =>
  allExpenses.value.reduce((sum, e) => sum + e.attachments.filter((f) => f.ocr_status !== "success").length, 0)
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
  currentView.value = "my-expenses";
  draftToComplete.value = null;
  adminLedgerStatus.value = null;
  loadExpenses();
}

function handleLogout() {
  clearToken();
  user.value = null;
  currentView.value = "my-expenses";
  draftToComplete.value = null;
  adminLedgerStatus.value = null;
  allExpenses.value = [];
}

function handleSubmitted() {
  refreshKey.value += 1;
  currentView.value = "my-expenses";
  draftToComplete.value = null;
  loadExpenses();
}

function handleChangeView(view: ViewKey) {
  currentView.value = view;
  adminLedgerStatus.value = null;
}

function handleCompleteDraft(expense: Expense) {
  draftToComplete.value = expense;
  currentView.value = "new-expense";
}

function handleShowDraftsInLedger() {
  adminLedgerStatus.value = "draft";
  currentView.value = "admin-ledger";
}

onMounted(restoreSession);
watch(refreshKey, loadExpenses);
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
    <MyExpensesView
      v-show="currentView === 'my-expenses'"
      :user="user"
      :refresh-key="refreshKey"
      @complete-draft="handleCompleteDraft"
    />
    <NewExpenseView v-show="currentView === 'new-expense'" :user="user" :draft-expense="draftToComplete" @submitted="handleSubmitted" />
    <AdminLedgerView
      v-if="currentView === 'admin-ledger' && user.role === 'admin'"
      :initial-status="adminLedgerStatus"
    />
    <AdminUsersView v-if="currentView === 'admin-users' && user.role === 'admin'" />
    <ExportView v-if="currentView === 'export' && user.role === 'admin'" @show-drafts="handleShowDraftsInLedger" />
  </AppShell>
</template>
