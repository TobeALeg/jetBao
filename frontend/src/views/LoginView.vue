<script setup lang="ts">
import { onMounted, ref } from "vue";
import { Building2, LogIn } from "lucide-vue-next";
import { getAuthConfig, getSsoLoginUrl, login, setToken } from "../services/api";
import type { AuthConfig } from "../services/api";
import type { User } from "../types";

const emit = defineEmits<{
  "login-success": [user: User];
}>();

const username = ref("");
const password = ref("");
const loading = ref(false);
const error = ref("");
const authConfig = ref<AuthConfig | null>(null);

onMounted(async () => {
  const reason = new URLSearchParams(window.location.search).get("sso_error");
  if (reason === "access_not_provisioned") error.value = "企业身份验证成功，但尚未开通 JetBao 权限，请联系管理员。";
  if (reason === "identity_mismatch") error.value = "该企业邮箱与已有员工身份不一致，请联系管理员。";
  if (reason === "identity_exchange_failed") error.value = "统一登录暂时不可用，请稍后重试。";
  try {
    authConfig.value = await getAuthConfig();
  } catch {
    error.value ||= "无法读取登录配置";
  }
});

function startSso() {
  window.location.assign(getSsoLoginUrl());
}

async function submit() {
  loading.value = true;
  error.value = "";
  try {
    const result = await login(username.value, password.value);
    setToken(result.token);
    emit("login-success", result.user);
  } catch (err) {
    error.value = err instanceof Error ? err.message : "登录失败";
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <main class="grid min-h-screen bg-stone-50 px-4 py-10 text-ink">
    <div class="mx-auto flex w-full max-w-5xl items-center">
      <div class="grid w-full overflow-hidden rounded-xl border border-slate-200 bg-white shadow-line lg:grid-cols-[1fr_420px]">
        <section class="hidden border-r border-slate-200 bg-slate-50 p-10 lg:block">
          <div class="text-lg font-semibold text-ink">JetBao</div>
          <h1 class="mt-16 max-w-md text-4xl font-semibold leading-tight tracking-normal text-ink">
            内部报销整理系统
          </h1>
          <p class="mt-5 max-w-md text-sm leading-6 text-slate-600">
            提交、查重、台账筛选和 Excel 导出放在同一个清爽工作台里。
          </p>
          <div class="mt-16 grid grid-cols-3 divide-x divide-slate-200 border-y border-slate-200">
            <div class="py-4">
              <div class="text-xl font-semibold">OCR</div>
              <div class="mt-1 text-xs text-slate-500">辅助识别</div>
            </div>
            <div class="px-4 py-4">
              <div class="text-xl font-semibold">Hash</div>
              <div class="mt-1 text-xs text-slate-500">重复提醒</div>
            </div>
            <div class="px-4 py-4">
              <div class="text-xl font-semibold">XLSX</div>
              <div class="mt-1 text-xs text-slate-500">月底导出</div>
            </div>
          </div>
        </section>

        <section class="p-6 sm:p-8">
          <div class="mb-8 lg:hidden">
            <div class="text-lg font-semibold text-ink">JetBao</div>
            <p class="mt-2 text-sm text-slate-500">内部报销整理系统</p>
          </div>

          <h2 class="text-xl font-semibold tracking-normal text-ink">登录</h2>
          <p class="muted mt-2">使用公司的统一企业邮箱身份进入系统。</p>

          <div v-if="authConfig?.sso_enabled" class="mt-8">
            <button class="primary-button w-full" type="button" @click="startSso">
              <Building2 class="h-4 w-4" />
              使用企业邮箱登录
            </button>
          </div>

          <div v-if="authConfig?.sso_enabled && authConfig?.legacy_enabled" class="my-6 flex items-center gap-3 text-xs text-slate-400">
            <div class="h-px flex-1 bg-slate-200"></div>
            迁移期间账号登录
            <div class="h-px flex-1 bg-slate-200"></div>
          </div>

          <form v-if="authConfig?.legacy_enabled" :class="authConfig?.sso_enabled ? '' : 'mt-8'" class="space-y-5" @submit.prevent="submit">
            <div>
              <label class="field-label" for="username">账号</label>
              <input id="username" v-model="username" class="field-input mt-1" autocomplete="username" />
            </div>
            <div>
              <label class="field-label" for="password">密码</label>
              <input id="password" v-model="password" class="field-input mt-1" autocomplete="current-password" type="password" />
            </div>

            <button class="primary-button w-full" type="submit" :disabled="loading">
              <LogIn class="h-4 w-4" />
              {{ loading ? "正在登录..." : "登录系统" }}
            </button>
          </form>
          <p v-if="error" class="mt-5 rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-700">{{ error }}</p>
        </section>
      </div>
    </div>
  </main>
</template>
