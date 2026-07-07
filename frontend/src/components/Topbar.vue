<script setup lang="ts">
import { reactive, ref } from "vue";
import { KeyRound, Loader2, LogOut, X } from "lucide-vue-next";
import { changePassword } from "../services/api";
import type { User, WorkspaceMode } from "../types";

defineProps<{
  user: User;
  workspaceMode: WorkspaceMode;
}>();

defineEmits<{
  logout: [];
}>();

const showPasswordForm = ref(false);
const saving = ref(false);
const error = ref("");
const form = reactive({
  current_password: "",
  new_password: "",
  confirm_password: ""
});

function resetForm() {
  form.current_password = "";
  form.new_password = "";
  form.confirm_password = "";
  error.value = "";
}

function closePasswordForm() {
  showPasswordForm.value = false;
  resetForm();
}

async function submitPasswordChange() {
  error.value = "";
  if (form.new_password !== form.confirm_password) {
    error.value = "两次输入的新密码不一致";
    return;
  }
  saving.value = true;
  try {
    await changePassword({
      current_password: form.current_password,
      new_password: form.new_password
    });
    closePasswordForm();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "修改失败";
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <header class="flex h-16 items-center justify-between border-b border-slate-200 bg-white px-4 sm:px-6 lg:px-8">
    <div class="min-w-0">
      <div class="truncate text-sm font-medium text-ink">{{ user.company_entity }}</div>
      <div class="text-xs text-slate-500">
        {{ user.role === "admin" ? (workspaceMode === "admin" ? "管理员 · 管理区" : "管理员 · 个人区") : "员工" }}
      </div>
    </div>
    <div class="flex items-center gap-3">
      <div class="hidden text-right sm:block">
        <div class="text-sm font-medium text-slate-800">{{ user.employee_name }}</div>
        <div class="text-xs text-slate-500">@{{ user.username }}</div>
      </div>
      <button class="secondary-button h-9 px-3" type="button" @click="showPasswordForm = true">
        <KeyRound class="h-4 w-4" />
        <span class="hidden sm:inline">改密码</span>
      </button>
      <button class="secondary-button h-9 px-3" type="button" @click="$emit('logout')">
        <LogOut class="h-4 w-4" />
        <span class="hidden sm:inline">退出</span>
      </button>
    </div>
  </header>

  <div v-if="showPasswordForm" class="fixed inset-0 z-50 grid place-items-center bg-slate-950/25 px-4 py-6">
    <form class="w-full max-w-sm rounded-lg border border-slate-200 bg-white p-5 shadow-line" @submit.prevent="submitPasswordChange">
      <div class="flex items-center justify-between gap-3">
        <div>
          <h2 class="section-title">修改密码</h2>
          <p class="muted mt-1">下次登录使用新密码。</p>
        </div>
        <button class="secondary-button h-9 w-9 px-0" type="button" aria-label="关闭" @click="closePasswordForm">
          <X class="h-4 w-4" />
        </button>
      </div>

      <div class="mt-5 space-y-3">
        <div>
          <label class="field-label" for="current-password">当前密码</label>
          <input
            id="current-password"
            v-model="form.current_password"
            autocomplete="current-password"
            class="field-input mt-1"
            required
            type="password"
          />
        </div>
        <div>
          <label class="field-label" for="new-password">新密码</label>
          <input
            id="new-password"
            v-model="form.new_password"
            autocomplete="new-password"
            class="field-input mt-1"
            minlength="6"
            required
            type="password"
          />
        </div>
        <div>
          <label class="field-label" for="confirm-password">确认新密码</label>
          <input
            id="confirm-password"
            v-model="form.confirm_password"
            autocomplete="new-password"
            class="field-input mt-1"
            minlength="6"
            required
            type="password"
          />
        </div>
      </div>

      <p v-if="error" class="mt-4 rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-700">{{ error }}</p>

      <div class="mt-5 flex justify-end gap-2">
        <button class="secondary-button" type="button" @click="closePasswordForm">取消</button>
        <button class="primary-button" type="submit" :disabled="saving">
          <Loader2 v-if="saving" class="h-4 w-4 animate-spin" />
          保存
        </button>
      </div>
    </form>
  </div>
</template>
