<script setup lang="ts">
import { reactive, ref } from "vue";
import { Building2, KeyRound, Loader2, UserRound } from "lucide-vue-next";
import { changePassword } from "../services/api";
import type { User } from "../types";

defineProps<{
  user: User;
}>();

const saving = ref(false);
const error = ref("");
const success = ref("");
const form = reactive({
  current_password: "",
  new_password: "",
  confirm_password: "",
});

async function submitPasswordChange() {
  error.value = "";
  success.value = "";
  if (form.new_password !== form.confirm_password) {
    error.value = "两次输入的新密码不一致";
    return;
  }
  saving.value = true;
  try {
    await changePassword({
      current_password: form.current_password,
      new_password: form.new_password,
    });
    form.current_password = "";
    form.new_password = "";
    form.confirm_password = "";
    success.value = "密码已更新";
  } catch (err) {
    error.value = err instanceof Error ? err.message : "修改失败";
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <div class="mx-auto max-w-3xl space-y-6">
    <div>
      <h1 class="page-title">个人设置</h1>
      <p class="muted mt-1">查看账号信息并修改登录密码。</p>
    </div>

    <section class="tool-panel rounded-lg p-5">
      <h2 class="section-title">账号信息</h2>
      <div class="mt-4 space-y-4">
        <div class="flex items-start gap-3">
          <div class="grid h-9 w-9 shrink-0 place-items-center rounded-md bg-slate-100 text-slate-500">
            <UserRound class="h-4 w-4" />
          </div>
          <div>
            <p class="text-xs text-slate-500">姓名</p>
            <p class="mt-0.5 text-sm font-medium text-ink">{{ user.employee_name }}</p>
          </div>
        </div>
        <div class="flex items-start gap-3">
          <div class="grid h-9 w-9 shrink-0 place-items-center rounded-md bg-slate-100 text-slate-500">
            <UserRound class="h-4 w-4" />
          </div>
          <div>
            <p class="text-xs text-slate-500">用户名</p>
            <p class="mt-0.5 text-sm font-medium text-ink">@{{ user.username }}</p>
          </div>
        </div>
        <div class="flex items-start gap-3">
          <div class="grid h-9 w-9 shrink-0 place-items-center rounded-md bg-slate-100 text-slate-500">
            <Building2 class="h-4 w-4" />
          </div>
          <div>
            <p class="text-xs text-slate-500">公司主体</p>
            <p class="mt-0.5 text-sm font-medium text-ink">{{ user.company_entity }}</p>
          </div>
        </div>
      </div>
    </section>

    <section class="tool-panel rounded-lg p-5">
      <div class="flex items-center gap-2">
        <KeyRound class="h-4 w-4 text-teal-700" />
        <h2 class="section-title">修改密码</h2>
      </div>
      <form class="mt-4 space-y-3" @submit.prevent="submitPasswordChange">
        <div>
          <label class="field-label" for="settings-current-password">当前密码</label>
          <input
            id="settings-current-password"
            v-model="form.current_password"
            autocomplete="current-password"
            class="field-input mt-1"
            required
            type="password"
          />
        </div>
        <div>
          <label class="field-label" for="settings-new-password">新密码</label>
          <input
            id="settings-new-password"
            v-model="form.new_password"
            autocomplete="new-password"
            class="field-input mt-1"
            minlength="6"
            required
            type="password"
          />
        </div>
        <div>
          <label class="field-label" for="settings-confirm-password">确认新密码</label>
          <input
            id="settings-confirm-password"
            v-model="form.confirm_password"
            autocomplete="new-password"
            class="field-input mt-1"
            minlength="6"
            required
            type="password"
          />
        </div>
        <p v-if="error" class="rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-700">{{ error }}</p>
        <p v-if="success" class="rounded-md bg-teal-50 px-3 py-2 text-sm text-teal-800">{{ success }}</p>
        <div class="pt-1">
          <button class="primary-button" type="submit" :disabled="saving">
            <Loader2 v-if="saving" class="h-4 w-4 animate-spin" />
            保存新密码
          </button>
        </div>
      </form>
    </section>
  </div>
</template>
