<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { Save, UserPlus } from "lucide-vue-next";
import { createUser, deactivateUser, getAuthConfig, listUsers, updateUser } from "../services/api";
import type { AuthConfig } from "../services/api";
import { COMPANY_ENTITIES } from "../constants/companyEntities";
import type { AdminUser, AdminUserCreatePayload, Role } from "../types";

const users = ref<AdminUser[]>([]);
const loading = ref(false);
const saving = ref(false);
const error = ref("");
const success = ref("");
const authConfig = ref<AuthConfig | null>(null);

const newUser = reactive<AdminUserCreatePayload>({
  username: "",
  email: "",
  password: "",
  role: "employee",
  employee_name: "",
  company_entity: ""
});

const editingPasswords = reactive<Record<number, string>>({});

async function load() {
  loading.value = true;
  error.value = "";
  try {
    [users.value, authConfig.value] = await Promise.all([listUsers(), getAuthConfig()]);
  } catch (err) {
    error.value = err instanceof Error ? err.message : "加载员工失败";
  } finally {
    loading.value = false;
  }
}

async function create() {
  saving.value = true;
  error.value = "";
  success.value = "";
  try {
    const payload = { ...newUser };
    if (!authConfig.value?.legacy_enabled) delete payload.password;
    await createUser(payload);
    Object.assign(newUser, {
      username: "",
      email: "",
      password: "",
      role: "employee" as Role,
      employee_name: "",
      company_entity: ""
    });
    success.value = "员工账号已创建";
    await load();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "创建失败";
  } finally {
    saving.value = false;
  }
}

async function save(user: AdminUser) {
  saving.value = true;
  error.value = "";
  success.value = "";
  try {
    const password = editingPasswords[user.id]?.trim();
    await updateUser(user.id, {
      role: user.role,
      email: user.email?.trim() || "",
      employee_name: user.employee_name,
      company_entity: user.company_entity,
      is_active: user.is_active,
      ...(password ? { password } : {})
    });
    editingPasswords[user.id] = "";
    success.value = "员工信息已保存";
    await load();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "保存失败";
  } finally {
    saving.value = false;
  }
}

async function deactivate(user: AdminUser) {
  saving.value = true;
  error.value = "";
  success.value = "";
  try {
    await deactivateUser(user.id);
    success.value = "账号已停用";
    await load();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "停用失败";
  } finally {
    saving.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div class="mx-auto max-w-7xl space-y-5">
    <div>
      <h1 class="page-title">管理</h1>
      <p class="muted mt-1">员工账号、角色和公司主体维护。</p>
    </div>

    <p v-if="error" class="rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-700">{{ error }}</p>
    <p v-if="success" class="rounded-md bg-teal-50 px-3 py-2 text-sm text-teal-800">{{ success }}</p>

    <section class="tool-panel rounded-lg p-5">
      <div class="mb-4">
        <h2 class="section-title">新增员工</h2>
      </div>
      <form class="grid gap-3 lg:grid-cols-6" @submit.prevent="create">
        <input v-model="newUser.username" class="field-input" placeholder="用户名" required />
        <input v-model="newUser.email" class="field-input" placeholder="企业邮箱" required type="email" />
        <input v-model="newUser.employee_name" class="field-input" placeholder="员工姓名" required />
        <select v-model="newUser.company_entity" class="field-input" required>
          <option value="" disabled>选择公司主体</option>
          <option v-for="company in COMPANY_ENTITIES" :key="company" :value="company">{{ company }}</option>
        </select>
        <select v-model="newUser.role" class="field-input">
          <option value="employee">员工</option>
          <option value="admin">管理员</option>
        </select>
        <input
          v-if="authConfig?.legacy_enabled"
          v-model="newUser.password"
          autocomplete="new-password"
          class="field-input"
          placeholder="初始密码"
          required
          type="password"
        />
        <div class="lg:col-span-6">
          <button class="primary-button" type="submit" :disabled="saving">
            <UserPlus class="h-4 w-4" />
            创建账号
          </button>
        </div>
      </form>
    </section>

    <section class="tool-panel overflow-hidden rounded-lg">
      <div class="border-b border-slate-200 px-5 py-4">
        <h2 class="section-title">员工列表</h2>
        <p class="muted mt-1">{{ loading ? "正在加载..." : `共 ${users.length} 个账号` }}</p>
      </div>

      <div v-if="loading" class="px-5 py-12 text-center text-sm text-slate-500">正在加载...</div>
      <div v-else class="overflow-x-auto">
        <div v-if="!users.length" class="empty-state">
          <div class="empty-state-icon">
            <UserPlus class="h-6 w-6" />
          </div>
          <div>
            <div class="text-sm font-medium text-slate-700">还没有员工账号</div>
            <div class="mt-1 text-xs text-slate-500">在上方表单创建第一个员工账号。</div>
          </div>
        </div>
        <table v-else class="min-w-full divide-y divide-slate-200 text-left text-sm">
          <thead class="bg-slate-50 text-xs font-medium uppercase tracking-normal text-slate-500">
            <tr>
              <th class="px-5 py-3">账号</th>
              <th class="px-5 py-3">企业邮箱</th>
              <th class="px-5 py-3">姓名</th>
              <th class="px-5 py-3">角色</th>
              <th class="px-5 py-3">绑定企业抬头</th>
              <th class="px-5 py-3">状态</th>
              <th v-if="authConfig?.legacy_enabled" class="px-5 py-3">重置密码</th>
              <th class="px-5 py-3">操作</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100 bg-white">
            <tr v-for="user in users" :key="user.id" class="align-top hover:bg-slate-50/70">
              <td class="whitespace-nowrap px-5 py-4 font-medium text-slate-900">{{ user.username }}</td>
              <td v-if="authConfig?.legacy_enabled" class="px-5 py-4">
                <input v-model="user.email" class="field-input min-w-56" placeholder="name@mentitrek.com" type="email" />
                <p v-if="user.identity_id" class="mt-1 text-xs text-teal-700">已绑定统一身份</p>
              </td>
              <td class="px-5 py-4">
                <input v-model="user.employee_name" class="field-input min-w-36" />
              </td>
              <td class="px-5 py-4">
                <select v-model="user.role" class="field-input min-w-28">
                  <option value="employee">员工</option>
                  <option value="admin">管理员</option>
                </select>
              </td>
              <td class="px-5 py-4">
                <select v-model="user.company_entity" class="field-input min-w-72">
                  <option v-for="company in COMPANY_ENTITIES" :key="company" :value="company">{{ company }}</option>
                </select>
              </td>
              <td class="px-5 py-4">
                <label class="flex h-10 items-center gap-2 text-sm text-slate-700">
                  <input v-model="user.is_active" class="h-4 w-4 rounded border-slate-300 text-teal-700" type="checkbox" />
                  启用
                </label>
              </td>
              <td class="px-5 py-4">
                <input v-model="editingPasswords[user.id]" autocomplete="new-password" class="field-input min-w-36" placeholder="留空不改" type="password" />
              </td>
              <td class="whitespace-nowrap px-5 py-4">
                <div class="flex gap-2">
                  <button class="secondary-button h-9 px-3" type="button" :disabled="saving" @click="save(user)">
                    <Save class="h-4 w-4" />
                    保存
                  </button>
                  <button class="secondary-button h-9 px-3 text-rose-700" type="button" :disabled="saving || !user.is_active" @click="deactivate(user)">
                    停用
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>
