<script setup lang="ts">
import { onMounted, ref } from "vue";
import AppShell from "./components/AppShell.vue";
import LoginView from "./views/LoginView.vue";
import MyExpensesView from "./views/MyExpensesView.vue";
import NewExpenseView from "./views/NewExpenseView.vue";
import AdminLedgerView from "./views/AdminLedgerView.vue";
import AdminUsersView from "./views/AdminUsersView.vue";
import ExportView from "./views/ExportView.vue";
import { clearToken, getMe, getToken } from "./services/api";
import type { User, ViewKey } from "./types";

const user = ref<User | null>(null);
const currentView = ref<ViewKey>("my-expenses");
const loadingSession = ref(true);
const refreshKey = ref(0);

async function restoreSession() {
  if (!getToken()) {
    loadingSession.value = false;
    return;
  }
  try {
    user.value = await getMe();
  } catch {
    clearToken();
  } finally {
    loadingSession.value = false;
  }
}

function handleLogin(nextUser: User) {
  user.value = nextUser;
  currentView.value = "my-expenses";
}

function handleLogout() {
  clearToken();
  user.value = null;
  currentView.value = "my-expenses";
}

function handleSubmitted() {
  refreshKey.value += 1;
  currentView.value = "my-expenses";
}

onMounted(restoreSession);
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
    @change-view="currentView = $event"
    @logout="handleLogout"
  >
    <MyExpensesView v-if="currentView === 'my-expenses'" :user="user" :refresh-key="refreshKey" />
    <NewExpenseView v-else-if="currentView === 'new-expense'" :user="user" @submitted="handleSubmitted" />
    <AdminLedgerView v-else-if="currentView === 'admin-ledger' && user.role === 'admin'" />
    <AdminUsersView v-else-if="currentView === 'admin-users' && user.role === 'admin'" />
    <ExportView v-else-if="currentView === 'export' && user.role === 'admin'" />
    <MyExpensesView v-else :user="user" :refresh-key="refreshKey" />
  </AppShell>
</template>
