<script setup lang="ts">
import { computed, reactive, ref } from "vue";
import { Save } from "lucide-vue-next";
import { currentMonth } from "../utils/format";
import type { Attachment, ExpenseCreatePayload, User } from "../types";

const props = defineProps<{
  user: User;
  attachments: Attachment[];
  submitting?: boolean;
}>();

const emit = defineEmits<{
  submit: [payload: ExpenseCreatePayload];
}>();

const form = reactive({
  category: "差旅交通",
  expense_month: currentMonth(),
  actual_amount: "",
  invoice_amount: "",
  is_substitute: false,
  substitute_reason: "",
  note: ""
});

const error = ref("");

const amountMismatch = computed(() => {
  if (!form.invoice_amount || !form.actual_amount) return false;
  return Number(form.invoice_amount).toFixed(2) !== Number(form.actual_amount).toFixed(2);
});

const needsReason = computed(() => form.is_substitute || amountMismatch.value);

function submit() {
  error.value = "";
  const actualAmount = Number(form.actual_amount);
  const invoiceAmount = form.is_substitute ? Number(form.invoice_amount) : actualAmount;

  if (!form.category || !form.expense_month || !actualAmount || actualAmount <= 0) {
    error.value = "请填写类别、月份和实际报销金额。";
    return;
  }
  if (form.is_substitute && (!invoiceAmount || invoiceAmount <= 0)) {
    error.value = "替票时需要填写发票金额。";
    return;
  }
  if (needsReason.value && !form.substitute_reason.trim()) {
    error.value = "替票或金额不一致时必须填写说明。";
    return;
  }

  emit("submit", {
    category: form.category,
    expense_month: form.expense_month,
    actual_amount: actualAmount,
    invoice_amount: invoiceAmount,
    is_substitute: form.is_substitute,
    substitute_reason: form.substitute_reason,
    note: form.note,
    attachment_ids: props.attachments.map((item) => item.id)
  });
}
</script>

<template>
  <section class="tool-panel rounded-lg">
    <div class="border-b border-slate-200 px-5 py-4">
      <h2 class="section-title">报销信息</h2>
      <p class="muted mt-1">公司主体由员工档案自动带出。</p>
    </div>

    <form class="space-y-5 p-5" @submit.prevent="submit">
      <div>
        <label class="field-label">公司主体</label>
        <div class="mt-1 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">
          {{ user.company_entity }}
        </div>
      </div>

      <div class="grid gap-4 sm:grid-cols-2">
        <div>
          <label class="field-label" for="category">报销类别</label>
          <select id="category" v-model="form.category" class="field-input mt-1">
            <option>差旅交通</option>
            <option>餐饮招待</option>
            <option>办公采购</option>
            <option>市场活动</option>
            <option>其他</option>
          </select>
        </div>
        <div>
          <label class="field-label" for="month">报销月份</label>
          <input id="month" v-model="form.expense_month" class="field-input mt-1" type="month" />
        </div>
      </div>

      <div class="grid gap-4 sm:grid-cols-2">
        <div>
          <label class="field-label" for="actual">实际报销金额</label>
          <input id="actual" v-model="form.actual_amount" class="field-input mt-1" min="0" step="0.01" type="number" />
        </div>
        <div v-if="form.is_substitute">
          <label class="field-label" for="invoice">发票金额</label>
          <input id="invoice" v-model="form.invoice_amount" class="field-input mt-1" min="0" step="0.01" type="number" />
        </div>
      </div>

      <label class="flex items-center gap-3 rounded-md border border-slate-200 bg-white px-3 py-3 text-sm text-slate-700">
        <input v-model="form.is_substitute" class="h-4 w-4 rounded border-slate-300 text-teal-700" type="checkbox" />
        <span>这笔报销是替票</span>
      </label>

      <div v-if="needsReason">
        <label class="field-label" for="reason">替票 / 金额差异说明</label>
        <textarea
          id="reason"
          v-model="form.substitute_reason"
          class="field-textarea mt-1"
          placeholder="说明为什么发票金额和实际报销金额不同，或为什么需要替票。"
        />
      </div>

      <div>
        <label class="field-label" for="note">备注</label>
        <textarea id="note" v-model="form.note" class="field-textarea mt-1" placeholder="可填写项目、客户或补充说明。" />
      </div>

      <p v-if="error" class="rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-700">{{ error }}</p>

      <button class="primary-button w-full sm:w-auto" type="submit" :disabled="submitting">
        <Save class="h-4 w-4" />
        {{ submitting ? "正在保存..." : "提交报销" }}
      </button>
    </form>
  </section>
</template>

