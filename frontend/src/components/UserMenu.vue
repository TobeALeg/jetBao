<script setup lang="ts">
import { onBeforeUnmount, reactive, ref, watch } from "vue";
import { KeyRound, Loader2, ChevronDown } from "lucide-vue-next";
import { changePassword } from "../services/api";
import type { User } from "../types";

const props = defineProps<{
  user: User;
}>();

const root = ref<HTMLElement | null>(null);
const open = ref(false);
const showPasswordForm = ref(false);

const saving = ref(false);
const error = ref("");
const success = ref("");
const form = reactive({
  current_password: "",
  new_password: "",
  confirm_password: "",
});

function close() {
  open.value = false;
  showPasswordForm.value = false;
  error.value = "";
  success.value = "";
}

function onPointerDown(event: PointerEvent) {
  if (root.value?.contains(event.target as Node)) return;
  close();
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === "Escape") close();
}

watch(open, (isOpen) => {
  if (isOpen) {
    document.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("keydown", onKeydown);
  } else {
    document.removeEventListener("pointerdown", onPointerDown);
    window.removeEventListener("keydown", onKeydown);
  }
});

onBeforeUnmount(() => {
  document.removeEventListener("pointerdown", onPointerDown);
  window.removeEventListener("keydown", onKeydown);
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
  <div ref="root" class="relative">
    <button
      class="flex items-center gap-2 rounded-control px-2 py-1 transition duration-1 ease-standard hover:bg-surface-soft focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      type="button"
      :aria-expanded="open"
      aria-haspopup="dialog"
      @click="open ? close() : (open = true)"
    >
      <span class="hidden text-right sm:block">
        <span class="block text-sm font-medium text-slate-800">{{ user.employee_name }}</span>
        <span class="block text-xs text-slate-500">{{ user.email || `@${user.username}` }}</span>
      </span>
      <span class="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-accent-soft text-xs font-semibold text-accent-ink sm:hidden">
        {{ user.employee_name.slice(0, 1) }}
      </span>
      <ChevronDown
        class="h-3.5 w-3.5 shrink-0 text-slate-400 transition-transform duration-2 ease-standard"
        :class="open ? 'rotate-180' : ''"
      />
    </button>

    <Transition name="pop">
      <div
        v-if="open"
        class="absolute right-0 top-full z-50 mt-2 w-72 origin-top-right overflow-hidden rounded-panel border border-hairline bg-white shadow-overlay"
        role="dialog"
        aria-label="账号信息"
      >
        <!-- 姓名 / 用户名已在触发器上显示，这里不再重复 -->
        <div class="px-4 py-3">
          <p class="text-xs text-slate-500">公司主体</p>
          <p class="mt-1 text-sm font-medium text-slate-800">{{ user.company_entity }}</p>
        </div>

        <!-- 仅本地密码账号可自助改密码；SSO 账号密码由企业统一管理 -->
        <div v-if="!user.email" class="border-t border-hairline px-4 py-3">
          <button
            v-if="!showPasswordForm"
            class="flex w-full items-center gap-2 rounded-control px-2 py-1.5 text-left text-sm text-slate-700 transition duration-1 ease-standard hover:bg-surface-soft"
            type="button"
            @click="showPasswordForm = true"
          >
            <KeyRound class="h-3.5 w-3.5 shrink-0 text-slate-400" />
            修改密码
          </button>

          <form v-else class="space-y-2.5" @submit.prevent="submitPasswordChange">
            <p class="text-xs font-semibold uppercase tracking-wide text-slate-400">修改密码</p>
            <div>
              <label class="field-label" for="user-menu-current-password">当前密码</label>
              <input
                id="user-menu-current-password"
                v-model="form.current_password"
                autocomplete="current-password"
                class="field-input mt-1"
                required
                type="password"
              />
            </div>
            <div>
              <label class="field-label" for="user-menu-new-password">新密码</label>
              <input
                id="user-menu-new-password"
                v-model="form.new_password"
                autocomplete="new-password"
                class="field-input mt-1"
                minlength="6"
                required
                type="password"
              />
            </div>
            <div>
              <label class="field-label" for="user-menu-confirm-password">确认新密码</label>
              <input
                id="user-menu-confirm-password"
                v-model="form.confirm_password"
                autocomplete="new-password"
                class="field-input mt-1"
                minlength="6"
                required
                type="password"
              />
            </div>
            <p v-if="error" class="rounded-control bg-state-danger-soft px-3 py-2 text-xs text-state-danger-ink">{{ error }}</p>
            <p v-if="success" class="rounded-control bg-state-action-soft px-3 py-2 text-xs text-state-action-ink">{{ success }}</p>
            <div class="flex items-center gap-2 pt-0.5">
              <button class="primary-button btn-xs" type="submit" :disabled="saving">
                <Loader2 v-if="saving" class="h-3.5 w-3.5 animate-spin" />
                保存新密码
              </button>
              <button class="secondary-button btn-xs" type="button" @click="showPasswordForm = false">取消</button>
            </div>
          </form>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
/* 弹窗入场：轻微位移 + 淡入，只动 transform / opacity */
.pop-enter-active,
.pop-leave-active {
  transition: opacity var(--dur-2) var(--ease-standard), transform var(--dur-2) var(--ease-standard);
}

.pop-enter-from,
.pop-leave-to {
  opacity: 0;
  transform: scale(0.97) translateY(-4px);
}

@media (prefers-reduced-motion: reduce) {
  .pop-enter-active,
  .pop-leave-active {
    transition: none !important;
  }
}
</style>
