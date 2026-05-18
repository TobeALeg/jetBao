<script setup lang="ts">
import { Search } from "lucide-vue-next";

const filters = defineModel<Record<string, string>>({ required: true });

defineEmits<{
  search: [];
}>();
</script>

<template>
  <section class="tool-panel rounded-lg p-4">
    <div class="grid gap-3 md:grid-cols-3 xl:grid-cols-6">
      <div>
        <label class="field-label" for="ledger-month">月份</label>
        <input id="ledger-month" v-model="filters.month" class="field-input mt-1" type="month" />
      </div>
      <div>
        <label class="field-label" for="ledger-company">公司主体</label>
        <input id="ledger-company" v-model="filters.company_entity" class="field-input mt-1" placeholder="全部" />
      </div>
      <div>
        <label class="field-label" for="ledger-employee">员工</label>
        <input id="ledger-employee" v-model="filters.employee" class="field-input mt-1" placeholder="姓名" />
      </div>
      <div>
        <label class="field-label" for="ledger-category">类别</label>
        <select id="ledger-category" v-model="filters.category" class="field-input mt-1">
          <option value="">全部</option>
          <option>差旅交通</option>
          <option>餐饮招待</option>
          <option>办公采购</option>
          <option>市场活动</option>
          <option>其他</option>
        </select>
      </div>
      <div>
        <label class="field-label" for="ledger-substitute">是否替票</label>
        <select id="ledger-substitute" v-model="filters.is_substitute" class="field-input mt-1">
          <option value="">全部</option>
          <option value="true">是</option>
          <option value="false">否</option>
        </select>
      </div>
      <div>
        <label class="field-label" for="ledger-duplicate">疑似重复</label>
        <select id="ledger-duplicate" v-model="filters.has_duplicate" class="field-input mt-1">
          <option value="">全部</option>
          <option value="true">是</option>
          <option value="false">否</option>
        </select>
      </div>
    </div>
    <div class="mt-4 flex justify-end">
      <button class="primary-button" type="button" @click="$emit('search')">
        <Search class="h-4 w-4" />
        筛选台账
      </button>
    </div>
  </section>
</template>

