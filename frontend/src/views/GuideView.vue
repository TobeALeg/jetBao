<script setup lang="ts">
import { computed } from "vue";
import {
  BookOpen,
  Building2,
  CheckCircle2,
  ClipboardList,
  FileText,
  HelpCircle,
  Home,
  ReceiptText,
  Settings,
  ShieldCheck,
  Upload,
  Users,
} from "lucide-vue-next";
import type { User } from "../types";

const props = defineProps<{
  user: User;
}>();

const isAdmin = computed(() => props.user.role === "admin");

const employeeSections = [
  { id: "overview", label: "系统简介" },
  { id: "login", label: "登录与账号" },
  { id: "submit", label: "提交报销" },
  { id: "status", label: "记录状态" },
  { id: "reject", label: "打回与修改" },
  { id: "faq", label: "常见问题" },
];

const adminSections = [
  { id: "overview", label: "系统简介" },
  { id: "login", label: "登录与账号" },
  { id: "submit", label: "个人报销" },
  { id: "ledger", label: "报销总览" },
  { id: "review", label: "审核与预览" },
  { id: "export", label: "导出归档" },
  { id: "users", label: "用户管理" },
  { id: "status", label: "状态说明" },
  { id: "faq", label: "常见问题" },
];

const sections = computed(() => (isAdmin.value ? adminSections : employeeSections));

function scrollTo(id: string) {
  document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
}
</script>

<template>
  <div class="mx-auto max-w-5xl space-y-8 pb-10">
    <header class="overflow-hidden rounded-2xl border border-teal-100 bg-gradient-to-br from-teal-50 via-white to-slate-50 p-6 sm:p-8">
      <div class="flex flex-wrap items-start gap-4">
        <div class="grid h-12 w-12 shrink-0 place-items-center rounded-xl bg-teal-700 text-white shadow-sm">
          <BookOpen class="h-6 w-6" />
        </div>
        <div class="min-w-0 flex-1">
          <h1 class="page-title">使用指南</h1>
          <p class="muted mt-2 max-w-2xl">
            JetBao 内部报销整理系统使用说明。{{ isAdmin ? "你当前为管理员，可查看全员台账、审核报销并管理账号。" : "你当前为员工，可在个人报销页提交与跟踪自己的报销。" }}
          </p>
        </div>
      </div>

      <div class="mt-6 flex flex-wrap gap-2">
        <button
          v-for="item in sections"
          :key="item.id"
          class="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:border-teal-300 hover:bg-teal-50 hover:text-teal-800"
          type="button"
          @click="scrollTo(item.id)"
        >
          {{ item.label }}
        </button>
      </div>
    </header>

    <div class="grid gap-6 lg:grid-cols-[220px_minmax(0,1fr)] lg:items-start">
      <aside class="hidden lg:block">
        <nav class="sticky top-6 space-y-1 rounded-lg border border-slate-200 bg-white p-3">
          <p class="px-2 pb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">目录</p>
          <button
            v-for="item in sections"
            :key="`nav-${item.id}`"
            class="block w-full rounded-md px-2 py-2 text-left text-sm text-slate-600 transition hover:bg-slate-50 hover:text-teal-800"
            type="button"
            @click="scrollTo(item.id)"
          >
            {{ item.label }}
          </button>
        </nav>
      </aside>

      <div class="space-y-6">
        <!-- 系统简介 -->
        <section id="overview" class="guide-section scroll-mt-6">
          <div class="guide-section-head">
            <Home class="h-5 w-5 text-teal-700" />
            <h2>系统简介</h2>
          </div>
          <div class="guide-card">
            <p>JetBao 用于公司内部报销材料的整理与提交。员工上传<strong>佐证材料</strong>和<strong>发票</strong>，系统自动识别发票信息并校验重复；管理员审核通过后归档，并可一键导出四页 Excel 与按公司、人员和报销类别整理的发票压缩包。</p>
            <div class="mt-4 grid gap-3 sm:grid-cols-2">
              <div class="rounded-lg border border-slate-200 bg-slate-50 p-4">
                <p class="text-xs font-semibold text-slate-500">员工可访问</p>
                <ul class="guide-list mt-2">
                  <li><Home class="guide-inline-icon" /> 个人报销</li>
                  <li><BookOpen class="guide-inline-icon" /> 使用指南</li>
                  <li><Settings class="guide-inline-icon" /> 个人设置</li>
                </ul>
              </div>
              <div class="rounded-lg border border-teal-100 bg-teal-50/60 p-4">
                <p class="text-xs font-semibold text-teal-700">管理员额外可访问</p>
                <ul class="guide-list mt-2">
                  <li><ReceiptText class="guide-inline-icon" /> 报销记录总览</li>
                  <li><ShieldCheck class="guide-inline-icon" /> 管理（用户与权限）</li>
                </ul>
              </div>
            </div>
          </div>
        </section>

        <!-- 登录与账号 -->
        <section id="login" class="guide-section scroll-mt-6">
          <div class="guide-section-head">
            <Building2 class="h-5 w-5 text-teal-700" />
            <h2>登录与账号</h2>
          </div>
          <div class="guide-card space-y-4">
            <ol class="guide-steps">
              <li>使用公司的<strong>企业邮箱</strong>在统一登录页接收验证码。</li>
              <li>顶部显示你的<strong>公司主体</strong>、<strong>姓名</strong>与<strong>角色</strong>（员工 / 管理员）。</li>
              <li>JetBao 权限和公司主体由管理员维护；企业邮箱只用于确认身份。</li>
            </ol>
            <p class="rounded-md border border-amber-100 bg-amber-50 px-3 py-2 text-sm text-amber-900">
              公司主体必须为系统允许的三家主体之一，发票购买方需与报销所属主体匹配（或按提示人工确认）。
            </p>
          </div>
        </section>

        <!-- 提交报销 -->
        <section id="submit" class="guide-section scroll-mt-6">
          <div class="guide-section-head">
            <Upload class="h-5 w-5 text-teal-700" />
            <h2>{{ isAdmin ? "个人报销（管理员也可为自己提交）" : "提交报销" }}</h2>
          </div>
          <div class="guide-card space-y-5">
            <p>进入「个人报销」，在页面上方填写报销信息并上传材料，下方「本月记录」可查看当前月份所有记录。</p>

            <div>
              <h3 class="guide-subtitle">推荐流程</h3>
              <ol class="guide-steps mt-3">
                <li>填写<strong>报销事项</strong>、<strong>金额</strong>、<strong>类别</strong>，按需选择是否<strong>替票</strong>。</li>
                <li>上传<strong>佐证材料</strong>（可多张，支持图片 / PDF），点击缩略图可预览。</li>
                <li>上传<strong>发票</strong>（可一次多选），系统自动 OCR 识别每张发票的金额、号码、票种、销售方等。</li>
                <li>确认识别结果无误后，点击<strong>提交报销</strong>；也可先「保存待补」稍后再补发票。</li>
              </ol>
            </div>

            <div class="grid gap-3 sm:grid-cols-2">
              <div class="rounded-lg border border-slate-200 p-4">
                <h3 class="guide-subtitle">替票选「否」</h3>
                <p class="mt-2 text-sm text-slate-600">一张发票只能用于一笔报销；一笔报销可包含多张发票，票面合计须与报销金额<strong>完全一致</strong>。</p>
              </div>
              <div class="rounded-lg border border-orange-100 bg-orange-50/50 p-4">
                <h3 class="guide-subtitle text-orange-800">替票选「是」</h3>
                <p class="mt-2 text-sm text-slate-600">发票与报销金额不一致时，需填写<strong>替票说明</strong>后再提交。</p>
              </div>
            </div>

            <div class="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
              <p class="font-medium text-slate-800">上传提示</p>
              <ul class="guide-list mt-2">
                <li>佐证材料不做发票 OCR，仅作报销依据留存。</li>
                <li>发票须为有效票据且识别到大于 0 的金额，否则会提示「此图片不是发票」。</li>
                <li>同文件重复上传会被标记为疑似重复，但不阻止提交。</li>
              </ul>
            </div>
          </div>
        </section>

        <!-- 管理员：报销总览 -->
        <section v-if="isAdmin" id="ledger" class="guide-section scroll-mt-6">
          <div class="guide-section-head">
            <ReceiptText class="h-5 w-5 text-teal-700" />
            <h2>报销记录总览</h2>
          </div>
          <div class="guide-card space-y-4">
            <p>查看<strong>所有人</strong>的报销记录，按年份、月份、公司主体、员工、状态筛选。记录按月份分组展开，可查看每笔金额与发票摘要。</p>
            <ul class="guide-list">
              <li>筛选后点击「查询」刷新列表；切换筛选条件会自动查询。</li>
              <li>「已提交」状态的记录等待管理员审核。</li>
              <li>「已完成」为审核通过记录，表格中以灰色显示。</li>
            </ul>
          </div>
        </section>

        <!-- 管理员：审核 -->
        <section v-if="isAdmin" id="review" class="guide-section scroll-mt-6">
          <div class="guide-section-head">
            <CheckCircle2 class="h-5 w-5 text-teal-700" />
            <h2>审核与预览</h2>
          </div>
          <div class="guide-card space-y-4">
            <ol class="guide-steps">
              <li>在总览中找到状态为<strong>已提交</strong>的记录，点击「预览」。</li>
              <li>在弹窗中查看佐证材料、发票缩略图及 OCR 识别信息，点击可放大预览。</li>
              <li>确认无误后点击「通过」；有问题点击「打回」并填写原因（可选）。</li>
              <li>已完成的记录可「撤销」审核，恢复为已提交状态。</li>
            </ol>
            <p class="text-sm text-slate-600">打回后员工会在「个人报销」看到<strong>已打回</strong>提示，可修改材料后重新提交。</p>
          </div>
        </section>

        <!-- 管理员：导出 -->
        <section v-if="isAdmin" id="export" class="guide-section scroll-mt-6">
          <div class="guide-section-head">
            <FileText class="h-5 w-5 text-teal-700" />
            <h2>导出归档</h2>
          </div>
          <div class="guide-card space-y-3">
            <p>在报销记录总览页，按当前筛选条件点击<strong>导出</strong>，会下载一个 ZIP 明细包，内含：</p>
            <ul class="guide-list">
              <li><strong>四页 Excel</strong>：总览、报销项汇总、发票明细、附件与待核对。</li>
              <li><strong>发票压缩包结构</strong>：山途远智几月报销 / 板块几月报销 / 人员几月报销 / 按报销事项命名的单据文件。</li>
            </ul>
          </div>
        </section>

        <!-- 管理员：用户管理 -->
        <section v-if="isAdmin" id="users" class="guide-section scroll-mt-6">
          <div class="guide-section-head">
            <Users class="h-5 w-5 text-teal-700" />
            <h2>用户管理</h2>
          </div>
          <div class="guide-card space-y-4">
            <p>在「管理」页可创建账号、修改角色与公司主体、重置密码或停用账号。</p>
            <div class="overflow-hidden rounded-lg border border-slate-200">
              <table class="min-w-full text-left text-sm">
                <thead class="bg-slate-50 text-xs text-slate-500">
                  <tr>
                    <th class="px-4 py-2.5">角色</th>
                    <th class="px-4 py-2.5">权限说明</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-slate-100">
                  <tr>
                    <td class="px-4 py-3 font-medium">员工</td>
                    <td class="px-4 py-3 text-slate-600">个人报销、个人设置、使用指南</td>
                  </tr>
                  <tr>
                    <td class="px-4 py-3 font-medium">管理员</td>
                    <td class="px-4 py-3 text-slate-600">上述全部 + 报销总览、审核、导出、用户管理</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </section>

        <!-- 状态说明 -->
        <section id="status" class="guide-section scroll-mt-6">
          <div class="guide-section-head">
            <ClipboardList class="h-5 w-5 text-teal-700" />
            <h2>记录状态说明</h2>
          </div>
          <div class="guide-card">
            <div class="space-y-3">
              <div class="flex flex-wrap items-center gap-3 rounded-lg border border-slate-200 p-3">
                <span class="status-pill bg-amber-100 text-amber-800">待补材料</span>
                <span class="text-sm text-slate-600">已创建报销，尚未上传佐证或发票不完整。</span>
              </div>
              <div class="flex flex-wrap items-center gap-3 rounded-lg border border-slate-200 p-3">
                <span class="status-pill bg-teal-50 text-teal-800">待提交</span>
                <span class="text-sm text-slate-600">材料齐全，尚未点击提交。</span>
              </div>
              <div class="flex flex-wrap items-center gap-3 rounded-lg border border-slate-200 p-3">
                <span class="status-pill bg-rose-50 text-rose-700">已打回</span>
                <span class="text-sm text-slate-600">管理员打回，需修改后重新提交；打回原因会显示在记录上。</span>
              </div>
              <div class="flex flex-wrap items-center gap-3 rounded-lg border border-slate-200 p-3">
                <span class="status-pill bg-slate-100 text-slate-600">已提交</span>
                <span class="text-sm text-slate-600">已提交待管理员审核；员工可「撤回」后修改（管理员总览中操作）。</span>
              </div>
              <div class="flex flex-wrap items-center gap-3 rounded-lg border border-slate-200 p-3">
                <span class="status-pill bg-slate-100 text-slate-500">已完成</span>
                <span class="text-sm text-slate-600">审核通过，灰色置底显示，不可再编辑。</span>
              </div>
            </div>
          </div>
        </section>

        <!-- 打回与修改（员工向） -->
        <section v-if="!isAdmin" id="reject" class="guide-section scroll-mt-6">
          <div class="guide-section-head">
            <CheckCircle2 class="h-5 w-5 text-teal-700" />
            <h2>打回与修改</h2>
          </div>
          <div class="guide-card space-y-3">
            <ol class="guide-steps">
              <li>被打回的记录会显示红色「已打回」标签及打回原因。</li>
              <li>点击「修改」打开编辑区，可更换佐证材料或发票。</li>
              <li>材料齐全后点击「重新提交」，再次进入待审核状态。</li>
            </ol>
          </div>
        </section>

        <!-- 常见问题 -->
        <section id="faq" class="guide-section scroll-mt-6">
          <div class="guide-section-head">
            <HelpCircle class="h-5 w-5 text-teal-700" />
            <h2>常见问题</h2>
          </div>
          <div class="guide-card divide-y divide-slate-100">
            <div class="guide-faq-item">
              <h3>为什么发票上传失败或提示不是发票？</h3>
              <p>请上传清晰的发票图片或 PDF。系统会 OCR 识别；若无法识别有效金额，会要求重新上传。</p>
            </div>
            <div class="guide-faq-item">
              <h3>选了「否」替票为什么还要求说明？</h3>
              <p>非替票时发票金额必须与报销金额一致。若不一致，请改选「替票」并填写说明，或调整报销金额。</p>
            </div>
            <div class="guide-faq-item">
              <h3>已提交的报销还能改吗？</h3>
              <p>在管理员审核前，可在「本月记录」点击「撤回」，回到待处理状态后再修改。审核通过后不可修改。</p>
            </div>
            <div v-if="isAdmin" class="guide-faq-item">
              <h3>员工能看到报销总览吗？</h3>
              <p>不能。报销记录总览、审核与导出仅管理员可见；员工只在个人报销页管理自己的记录。</p>
            </div>
            <div class="guide-faq-item">
              <h3>遇到问题找谁？</h3>
              <p>账号与权限问题请联系管理员；系统使用问题可将页面截图与操作步骤发给内部支持同事。</p>
            </div>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<style scoped>
.guide-section-head {
  @apply mb-3 flex items-center gap-2;
}

.guide-section-head h2 {
  @apply text-lg font-semibold text-ink;
}

.guide-card {
  @apply rounded-xl border border-slate-200 bg-white p-5 text-sm leading-relaxed text-slate-700 shadow-sm;
}

.guide-subtitle {
  @apply text-sm font-semibold text-slate-800;
}

.guide-steps {
  @apply list-decimal space-y-2 pl-5 text-slate-700;
}

.guide-list {
  @apply space-y-1.5 text-sm text-slate-600;
}

.guide-list li {
  @apply flex items-start gap-2;
}

.guide-inline-icon {
  @apply mt-0.5 h-3.5 w-3.5 shrink-0 text-teal-700;
}

.guide-faq-item {
  @apply py-4 first:pt-0 last:pb-0;
}

.guide-faq-item h3 {
  @apply text-sm font-semibold text-slate-900;
}

.guide-faq-item p {
  @apply mt-1.5 text-sm text-slate-600;
}
</style>
