<script setup lang="ts">
import { computed } from "vue";
import { BookOpen, CheckCircle2, Home, ReceiptText, ShieldCheck, Upload, X } from "lucide-vue-next";
import type { User } from "../types";

const props = defineProps<{
  open: boolean;
  user: User;
}>();

const emit = defineEmits<{
  dismiss: [];
  "view-full-guide": [];
}>();

const isAdmin = computed(() => props.user.role === "admin");
</script>

<template>
  <Teleport to="body">
    <div
      v-if="open"
      class="fixed inset-0 z-[60] flex items-center justify-center bg-slate-900/60 p-4"
      @click.self="emit('dismiss')"
    >
      <div
        class="relative flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="guide-welcome-title"
      >
        <div class="border-b border-teal-100 bg-gradient-to-r from-teal-50 to-white px-6 py-5">
          <button
            class="absolute right-4 top-4 inline-flex h-8 w-8 items-center justify-center rounded-md text-slate-500 transition hover:bg-white hover:text-slate-800"
            type="button"
            aria-label="关闭"
            @click="emit('dismiss')"
          >
            <X class="h-4 w-4" />
          </button>
          <div class="flex items-start gap-3 pr-10">
            <div class="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-teal-700 text-white">
              <BookOpen class="h-5 w-5" />
            </div>
            <div>
              <p class="text-xs font-semibold uppercase tracking-wide text-teal-700">欢迎，{{ user.employee_name }}</p>
              <h2 id="guide-welcome-title" class="mt-1 text-xl font-semibold text-ink">JetBao 使用指南</h2>
              <p class="mt-1 text-sm text-slate-600">首次登录请先了解以下要点，之后可在侧栏「使用指南」随时查看。</p>
            </div>
          </div>
        </div>

        <div class="flex-1 space-y-4 overflow-y-auto px-6 py-5 text-sm text-slate-700">
          <section class="rounded-xl border border-slate-200 bg-slate-50 p-4">
            <div class="mb-2 flex items-center gap-2 font-semibold text-slate-900">
              <Home class="h-4 w-4 text-teal-700" />
              个人报销
            </div>
            <ol class="list-decimal space-y-1.5 pl-5">
              <li>填写报销事项、金额、类别，选择是否替票。</li>
              <li>上传佐证材料（可多张）和发票（一次 1 张，自动识别）。</li>
              <li>材料齐全后点击「提交报销」，等待管理员审核。</li>
            </ol>
          </section>

          <section class="rounded-xl border border-slate-200 p-4">
            <div class="mb-2 flex items-center gap-2 font-semibold text-slate-900">
              <Upload class="h-4 w-4 text-teal-700" />
              替票与金额
            </div>
            <ul class="space-y-1.5">
              <li><strong>替票选「否」</strong>：发票金额须与报销金额完全一致。</li>
              <li><strong>替票选「是」</strong>：金额不一致时需填写替票说明。</li>
            </ul>
          </section>

          <section v-if="isAdmin" class="rounded-xl border border-teal-100 bg-teal-50/50 p-4">
            <div class="mb-2 flex items-center gap-2 font-semibold text-teal-900">
              <ReceiptText class="h-4 w-4" />
              管理员：报销记录总览
            </div>
            <ul class="space-y-1.5">
              <li>查看全员报销，按月份 / 员工 / 状态筛选。</li>
              <li>点击「预览」查看佐证与发票，「通过」或「打回」。</li>
              <li>可一键导出四页 Excel 与按板块整理的发票压缩包。</li>
            </ul>
          </section>

          <section v-if="isAdmin" class="rounded-xl border border-slate-200 p-4">
            <div class="mb-2 flex items-center gap-2 font-semibold text-slate-900">
              <ShieldCheck class="h-4 w-4 text-teal-700" />
              管理员：用户管理
            </div>
            <p>在「管理」页创建员工 / 管理员账号，设置公司主体与角色。</p>
          </section>

          <section class="rounded-xl border border-slate-200 p-4">
            <div class="mb-2 flex items-center gap-2 font-semibold text-slate-900">
              <CheckCircle2 class="h-4 w-4 text-teal-700" />
              状态速览
            </div>
            <div class="flex flex-wrap gap-2">
              <span class="status-pill bg-amber-100 text-amber-800">待补材料</span>
              <span class="status-pill bg-teal-50 text-teal-800">待提交</span>
              <span class="status-pill bg-rose-50 text-rose-700">已打回</span>
              <span class="status-pill bg-slate-100 text-slate-600">已提交</span>
              <span class="status-pill bg-slate-100 text-slate-500">已完成</span>
            </div>
          </section>
        </div>

        <div class="flex flex-wrap items-center justify-end gap-2 border-t border-slate-200 bg-white px-6 py-4">
          <button class="secondary-button h-10" type="button" @click="emit('view-full-guide')">查看完整指南</button>
          <button class="primary-button h-10" type="button" @click="emit('dismiss')">我知道了，开始使用</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
