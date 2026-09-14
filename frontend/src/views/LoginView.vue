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
  <main class="grid min-h-screen bg-surface-canvas px-4 py-10 text-slate-900">
    <div class="mx-auto flex w-full max-w-5xl items-center">
      <div class="grid w-full overflow-hidden rounded-panel border border-hairline bg-white shadow-overlay lg:grid-cols-[1fr_420px]">
        <!-- 左侧：品牌块。用业务语言，不用 OCR / Hash 这类内部术语 -->
        <section class="hidden flex-col justify-between border-r border-hairline bg-accent-soft p-10 lg:flex">
          <div class="flex items-center gap-2.5">
            <span class="grid h-9 w-9 shrink-0 place-items-center rounded-control bg-accent text-xs font-semibold text-white" aria-hidden="true">JB</span>
            <span class="text-sm font-semibold text-slate-900">JetBao</span>
          </div>

          <div>
            <h1 class="max-w-md text-[32px] font-semibold leading-tight tracking-tight text-slate-900">
              内部报销整理系统
            </h1>
            <p class="mt-4 max-w-md text-sm leading-6 text-slate-600">
              上传发票即可自动识别金额与抬头，重复票据会提前提醒；月底按公司主体、人员和类别一键导出。
            </p>
          </div>

          <div class="grid grid-cols-3 gap-px overflow-hidden rounded-control border border-accent-line bg-accent-line">
            <div class="bg-white px-4 py-3">
              <div class="text-[13px] font-semibold text-slate-900">自动识别</div>
              <div class="mt-1 text-xs text-slate-500">读取票面金额与抬头</div>
            </div>
            <div class="bg-white px-4 py-3">
              <div class="text-[13px] font-semibold text-slate-900">重复提醒</div>
              <div class="mt-1 text-xs text-slate-500">同票提前预警</div>
            </div>
            <div class="bg-white px-4 py-3">
              <div class="text-[13px] font-semibold text-slate-900">一键导出</div>
              <div class="mt-1 text-xs text-slate-500">台账与发票归档</div>
            </div>
          </div>
        </section>

        <section class="p-6 sm:p-8">
          <div class="mb-8 flex items-center gap-2.5 lg:hidden">
            <span class="grid h-8 w-8 shrink-0 place-items-center rounded-control bg-accent text-[11px] font-semibold text-white" aria-hidden="true">JB</span>
            <span>
              <span class="block text-sm font-semibold text-slate-900">JetBao</span>
              <span class="block text-xs text-slate-500">内部报销整理系统</span>
            </span>
          </div>

          <h2 class="section-title">登录</h2>
          <p class="muted mt-2">使用公司的统一企业邮箱身份进入系统。</p>

          <div v-if="authConfig?.sso_enabled" class="mt-8">
            <button class="primary-button is-anchor btn-lg w-full" type="button" @click="startSso">
              <Building2 class="h-4 w-4" />
              使用企业邮箱登录
            </button>
          </div>

          <div v-if="authConfig?.sso_enabled && authConfig?.legacy_enabled" class="my-6 flex items-center gap-3 text-xs text-slate-400">
            <div class="h-px flex-1 bg-hairline"></div>
            迁移期间账号登录
            <div class="h-px flex-1 bg-hairline"></div>
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

            <!-- SSO 是首选路径，只有它拿实心；账号登录降为柔和档，避免同屏两个实心块 -->
            <button
              :class="authConfig?.sso_enabled ? 'primary-button' : 'primary-button is-anchor'"
              class="w-full"
              type="submit"
              :disabled="loading"
            >
              <LogIn class="h-4 w-4" />
              {{ loading ? "正在登录..." : "登录系统" }}
            </button>
          </form>
          <p v-if="error" class="mt-5 rounded-control bg-state-danger-soft px-3 py-2 text-sm text-state-danger-ink">{{ error }}</p>
        </section>
      </div>
    </div>
  </main>
</template>
