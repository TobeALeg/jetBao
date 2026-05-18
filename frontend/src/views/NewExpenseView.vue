<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { AlertTriangle, CheckCircle2, Send } from "lucide-vue-next";
import InvoiceUploadPanel from "../components/InvoiceUploadPanel.vue";
import { createExpensesBatch } from "../services/api";
import { currentReimbursementMonth, formatCurrency } from "../utils/format";
import type { Attachment, ExpenseItemCreatePayload, User } from "../types";

const props = defineProps<{
  user: User;
}>();

const emit = defineEmits<{
  submitted: [];
}>();

interface DraftItem {
  local_id: string;
  attachment_id: number;
  attachment_name: string;
  invoice_item_index: number;
  category: string;
  expense_month: string;
  invoice_amount: number | null;
  invoice_buyer: string;
  invoice_number: string;
  invoice_date: string;
  invoice_type: string;
  page: string;
  is_substitute: boolean;
  actual_amount: string;
  substitute_reason: string;
  note: string;
  submitted?: boolean;
}

const attachments = ref<Attachment[]>([]);
const draftItems = ref<DraftItem[]>([]);
const submitting = ref(false);
const error = ref("");
const success = ref("");
const expenseMonth = ref(currentReimbursementMonth());

const activeDraftItems = computed(() => draftItems.value.filter((item) => !item.submitted));
const validDraftItems = computed(() => activeDraftItems.value.filter((item) => validationErrors(item).length === 0));
const invalidDraftItems = computed(() => activeDraftItems.value.filter((item) => validationErrors(item).length > 0));

watch(expenseMonth, (month) => {
  draftItems.value.forEach((item) => {
    if (!item.submitted) item.expense_month = month;
  });
});

function addAttachment(attachment: Attachment) {
  attachments.value = [attachment, ...attachments.value];
  const generated = invoiceItemsOf(attachment).map((item, index) => draftFromInvoiceItem(attachment, item, index));
  draftItems.value = [...draftItems.value, ...generated];
}

function removeAttachment(id: number) {
  const removed = attachments.value.find((item) => item.id === id);
  if (removed?.preview_url) URL.revokeObjectURL(removed.preview_url);
  attachments.value = attachments.value.filter((item) => item.id !== id);
  draftItems.value = draftItems.value.filter((item) => item.attachment_id !== id);
}

function invoiceItemsOf(attachment: Attachment): Array<Record<string, unknown>> {
  const items = attachment.ocr_result.invoice_items;
  return Array.isArray(items) ? (items as Array<Record<string, unknown>>) : [];
}

function draftFromInvoiceItem(attachment: Attachment, item: Record<string, unknown>, index: number): DraftItem {
  const amount = numberValue(item.amount);
  return {
    local_id: `${attachment.id}-${index}`,
    attachment_id: attachment.id,
    attachment_name: attachment.original_filename,
    invoice_item_index: index,
    category: categoryFromInvoice(item),
    expense_month: expenseMonth.value,
    invoice_amount: amount,
    invoice_buyer: textValue(item.buyer),
    invoice_number: textValue(item.invoice_number),
    invoice_date: textValue(item.date),
    invoice_type: textValue(item.sub_type_description) || textValue(item.type_description) || "票据",
    page: textValue(item.page),
    is_substitute: false,
    actual_amount: amount === null ? "" : String(amount),
    substitute_reason: "",
    note: ""
  };
}

function textValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  return String(value).trim();
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && value > 0 ? value : null;
}

function categoryFromInvoice(item: Record<string, unknown>): string {
  const text = [item.sub_type_description, item.type_description, item.title, item.summary]
    .map(textValue)
    .join(" ");
  if (/火车|铁路|机票|航空|出租|客运|通行费|交通|行程单/.test(text)) return "差旅交通";
  if (/餐饮|餐费|食品|外卖|饭店|餐厅/.test(text)) return "餐饮招待";
  if (/办公|耗材|打印|文具|设备|用品/.test(text)) return "办公采购";
  if (/广告|物料|展会|活动|市场|推广/.test(text)) return "市场活动";
  return "其他";
}

function companyTitlesMatch(recognizedBuyer: string, expectedCompany: string): boolean {
  const recognized = normalizeCompany(recognizedBuyer);
  const expected = normalizeCompany(expectedCompany);
  if (!recognized || !expected) return false;
  return recognized === expected || recognized.includes(expected) || expected.includes(recognized);
}

function normalizeCompany(value: string): string {
  return value.replace(/购买方|付款方|名称/g, "").replace(/[\s:：,，.。()（）[\]【】《》<>"']/g, "");
}

function validationErrors(item: DraftItem): string[] {
  const errors: string[] = [];
  if (item.invoice_amount === null) errors.push("未识别到发票金额");
  if (!item.invoice_buyer) {
    errors.push("未识别到企业抬头");
  } else if (!companyTitlesMatch(item.invoice_buyer, props.user.company_entity)) {
    errors.push("抬头不匹配");
  }
  if (item.is_substitute) {
    const actual = Number(item.actual_amount);
    if (!actual || actual <= 0) errors.push("替票需填写实际报销金额");
    if (!item.substitute_reason.trim()) errors.push("替票需填写说明");
  }
  return errors;
}

function toggleSubstitute(item: DraftItem) {
  if (!item.is_substitute && item.invoice_amount !== null) {
    item.actual_amount = String(item.invoice_amount);
    item.substitute_reason = "";
  } else {
    item.actual_amount = "";
  }
}

function removeDraftItem(localId: string) {
  draftItems.value = draftItems.value.filter((item) => item.local_id !== localId);
}

function payloadFromDraft(item: DraftItem): ExpenseItemCreatePayload {
  return {
    attachment_id: item.attachment_id,
    invoice_item_index: item.invoice_item_index,
    category: item.category,
    expense_month: item.expense_month,
    actual_amount: item.is_substitute ? Number(item.actual_amount) : null,
    is_substitute: item.is_substitute,
    substitute_reason: item.substitute_reason,
    note: item.note
  };
}

async function submitValidItems() {
  if (!validDraftItems.value.length) {
    error.value = "没有可提交的票据记录。";
    return;
  }
  submitting.value = true;
  error.value = "";
  success.value = "";
  const itemsToSubmit = [...validDraftItems.value];
  try {
    await createExpensesBatch(itemsToSubmit.map(payloadFromDraft));
    const submittedIds = new Set(itemsToSubmit.map((item) => item.local_id));
    draftItems.value = draftItems.value.filter((item) => !submittedIds.has(item.local_id));
    success.value = `已提交 ${itemsToSubmit.length} 条${draftItems.value.length ? `，${draftItems.value.length} 条需处理` : ""}`;
    if (!draftItems.value.length) {
      emit("submitted");
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : "提交失败";
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <div class="mx-auto max-w-7xl space-y-5">
    <div>
      <h1 class="page-title">新建报销</h1>
      <p class="muted mt-1">上传发票后自动生成报销记录。抬头不匹配或金额缺失的记录不会提交。</p>
    </div>

    <p v-if="error" class="rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-700">{{ error }}</p>
    <p v-if="success" class="rounded-md bg-teal-50 px-3 py-2 text-sm text-teal-800">{{ success }}</p>

    <div class="grid gap-5 xl:grid-cols-[minmax(0,1fr)_430px]">
      <section class="tool-panel rounded-lg">
        <div class="flex flex-col gap-4 border-b border-slate-200 px-5 py-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h2 class="section-title">待确认报销记录</h2>
            <p class="muted mt-1">每张识别出的票据生成一条记录。</p>
          </div>
          <div class="w-full lg:w-48">
            <label class="field-label" for="expense-month">报销月份</label>
            <input id="expense-month" v-model="expenseMonth" class="field-input mt-1" type="month" />
          </div>
        </div>

        <div class="grid divide-y divide-slate-200 sm:grid-cols-3 sm:divide-x sm:divide-y-0">
          <div class="px-5 py-4">
            <div class="text-xs text-slate-500">可提交</div>
            <div class="mt-1 text-2xl font-semibold text-ink">{{ validDraftItems.length }}</div>
          </div>
          <div class="px-5 py-4">
            <div class="text-xs text-slate-500">需处理</div>
            <div class="mt-1 text-2xl font-semibold text-amber-700">{{ invalidDraftItems.length }}</div>
          </div>
          <div class="px-5 py-4">
            <div class="text-xs text-slate-500">绑定企业</div>
            <div class="mt-1 truncate text-sm font-medium text-ink">{{ user.company_entity }}</div>
          </div>
        </div>

        <div v-if="!activeDraftItems.length" class="px-5 py-12 text-center text-sm text-slate-500">
          上传发票后会在这里生成待确认记录。
        </div>

        <div v-else class="divide-y divide-slate-100">
          <article v-for="item in activeDraftItems" :key="item.local_id" class="p-5">
            <div class="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <div class="min-w-0">
                <div class="flex flex-wrap items-center gap-2">
                  <h3 class="text-sm font-semibold text-ink">{{ item.invoice_type }}</h3>
                  <span v-if="validationErrors(item).length" class="status-pill bg-amber-50 text-amber-700">
                    <AlertTriangle class="mr-1 h-3.5 w-3.5" />
                    {{ validationErrors(item).join("、") }}
                  </span>
                  <span v-else class="status-pill bg-teal-50 text-teal-700">
                    <CheckCircle2 class="mr-1 h-3.5 w-3.5" />
                    可提交
                  </span>
                </div>
                <p class="mt-1 truncate text-xs text-slate-500">{{ item.attachment_name }} · 页码 {{ item.page || "-" }}</p>
              </div>
              <button class="text-sm text-slate-500 hover:text-rose-700" type="button" @click="removeDraftItem(item.local_id)">
                移除
              </button>
            </div>

            <div class="mt-4 grid gap-4 lg:grid-cols-4">
              <div>
                <div class="text-xs text-slate-500">发票金额</div>
                <div class="mt-1 text-sm font-semibold text-ink">{{ formatCurrency(item.invoice_amount) }}</div>
              </div>
              <div>
                <div class="text-xs text-slate-500">识别抬头</div>
                <div class="mt-1 truncate text-sm text-slate-700">{{ item.invoice_buyer || "-" }}</div>
              </div>
              <div>
                <div class="text-xs text-slate-500">发票号码</div>
                <div class="mt-1 text-sm text-slate-700">{{ item.invoice_number || "-" }}</div>
              </div>
              <div>
                <div class="text-xs text-slate-500">发票日期</div>
                <div class="mt-1 text-sm text-slate-700">{{ item.invoice_date || "-" }}</div>
              </div>
            </div>

            <div class="mt-4 grid gap-4 lg:grid-cols-3">
              <div>
                <label class="field-label">类别</label>
                <select v-model="item.category" class="field-input mt-1">
                  <option>差旅交通</option>
                  <option>餐饮招待</option>
                  <option>办公采购</option>
                  <option>市场活动</option>
                  <option>其他</option>
                </select>
              </div>
              <label class="mt-6 flex h-10 items-center gap-3 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-700">
                <input v-model="item.is_substitute" class="h-4 w-4 rounded border-slate-300 text-teal-700" type="checkbox" @change="toggleSubstitute(item)" />
                <span>替票</span>
              </label>
              <div v-if="item.is_substitute">
                <label class="field-label">实际报销金额</label>
                <input v-model="item.actual_amount" class="field-input mt-1" min="0" step="0.01" type="number" />
              </div>
            </div>

            <div class="mt-4 grid gap-4 lg:grid-cols-2">
              <div v-if="item.is_substitute">
                <label class="field-label">替票说明</label>
                <textarea v-model="item.substitute_reason" class="field-textarea mt-1" placeholder="说明原始报销金额和替票原因。" />
              </div>
              <div>
                <label class="field-label">备注</label>
                <textarea v-model="item.note" class="field-textarea mt-1" placeholder="项目、客户或补充说明。" />
              </div>
            </div>
          </article>
        </div>

        <div class="flex justify-end border-t border-slate-200 px-5 py-4">
          <button class="primary-button" type="button" :disabled="submitting || !validDraftItems.length" @click="submitValidItems">
            <Send class="h-4 w-4" />
            {{ submitting ? "正在提交..." : `提交 ${validDraftItems.length} 条可报销记录` }}
          </button>
        </div>
      </section>

      <InvoiceUploadPanel :attachments="attachments" @uploaded="addAttachment" @remove="removeAttachment" />
    </div>
  </div>
</template>
