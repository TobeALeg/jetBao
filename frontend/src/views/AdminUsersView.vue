<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref } from "vue";
import { Eye, EyeOff, Save, Trash2, UserPlus } from "lucide-vue-next";
import InlineAccordionSelect from "../components/InlineAccordionSelect.vue";
import StatusToggle from "../components/StatusToggle.vue";
import { createUser, deleteUser, getAuthConfig, listUsers, updateUser } from "../services/api";
import type { AuthConfig } from "../services/api";
import { COMPANY_ENTITIES } from "../constants/companyEntities";
import type { AdminUser, AdminUserCreatePayload, AdminUserUpdatePayload, Role } from "../types";

const users = ref<AdminUser[]>([]);
const loading = ref(false);
const saving = ref(false);
const newUserError = ref("");
const usersError = ref("");
const success = ref("");
const authConfig = ref<AuthConfig | null>(null);
const originalUserValues = ref(new Map<number, AdminUserUpdatePayload>());
const newUserForm = ref<HTMLFormElement | null>(null);
const usersForm = ref<HTMLFormElement | null>(null);
const usersCard = ref<HTMLElement | null>(null);
const usersErrorShaking = ref(false);
const newPasswordVisible = ref(false);
const newUserCard = ref<HTMLElement | null>(null);
const cardShimmering = ref(false);
const cardHasError = ref(false);
const cardErrorShaking = ref(false);

const newUser = reactive<AdminUserCreatePayload>({
  username: "",
  email: "",
  password: "",
  role: "employee",
  employee_name: "",
  company_entity: ""
});

const editingPasswords = reactive<Record<number, string>>({});
const roleOptions = [
  { label: "员工", value: "employee" },
  { label: "管理员", value: "admin" }
];
const companyOptions = COMPANY_ENTITIES.map((company) => ({ label: company, value: company }));
const nameManagedBySso = computed(() => authConfig.value?.sso_enabled ?? false);
const passwordManagedLocally = computed(() => authConfig.value?.mode === "legacy");

function updatePayload(user: AdminUser): AdminUserUpdatePayload {
  const password = passwordManagedLocally.value ? editingPasswords[user.id]?.trim() : "";
  const payload: AdminUserUpdatePayload = {
    role: user.role,
    email: user.email?.trim() || "",
    company_entity: user.company_entity,
    is_active: user.is_active,
    ...(password ? { password } : {})
  };
  if (!nameManagedBySso.value) payload.employee_name = user.employee_name.trim();
  return payload;
}

function editableUserValues(user: AdminUser): AdminUserUpdatePayload {
  const { password: _password, ...payload } = updatePayload(user);
  return payload;
}

function rememberUsers(nextUsers: AdminUser[]) {
  originalUserValues.value = new Map(nextUsers.map((user) => [user.id, editableUserValues(user)]));
}

type EditableUserField = "email" | "employee_name" | "role" | "company_entity" | "is_active";

function fieldChanged(user: AdminUser, field: EditableUserField): boolean {
  return originalUserValues.value.get(user.id)?.[field] !== editableUserValues(user)[field];
}

function userChanged(user: AdminUser): boolean {
  const fields: EditableUserField[] = ["email", "role", "company_entity", "is_active"];
  if (!nameManagedBySso.value) fields.push("employee_name");
  return fields.some((field) => fieldChanged(user, field));
}

const usersToSave = computed(() =>
  users.value.filter(
    (user) =>
      userChanged(user) || (passwordManagedLocally.value && Boolean(editingPasswords[user.id]?.trim()))
  )
);
const hasPendingChanges = computed(() => usersToSave.value.length > 0);

function clearNewUserError() {
  newUserError.value = "";
  cardHasError.value = false;
  cardErrorShaking.value = false;
}

function clearUsersError() {
  usersError.value = "";
  usersErrorShaking.value = false;
}

async function showUsersError(message: string) {
  usersError.value = message;
  await nextTick();
  const surface = usersCard.value;
  if (!surface) return;
  usersErrorShaking.value = false;
  await nextTick();
  void surface.offsetWidth;
  usersErrorShaking.value = true;
  window.setTimeout(() => {
    usersErrorShaking.value = false;
  }, 300);
}

async function showNewUserError(message: string) {
  newUserError.value = message;
  cardHasError.value = true;
  await nextTick();
  const card = newUserCard.value;
  if (!card) return;
  cardErrorShaking.value = false;
  await nextTick();
  void card.offsetWidth;
  cardErrorShaking.value = true;
  window.setTimeout(() => {
    cardErrorShaking.value = false;
  }, 300);
}

async function validate(
  form: HTMLFormElement | null,
  errorHandler: (message: string) => Promise<void> = showUsersError
): Promise<boolean> {
  if (!form || form.checkValidity()) return true;
  await errorHandler("请检查未填写或格式不正确的内容");
  return false;
}

async function playCardShimmer() {
  cardShimmering.value = false;
  await nextTick();
  const card = newUserCard.value;
  if (!card) return;
  void card.offsetWidth;
  cardShimmering.value = true;
  window.setTimeout(() => {
    cardShimmering.value = false;
  }, 680);
}

async function load() {
  loading.value = true;
  clearUsersError();
  try {
    const [loadedUsers, loadedAuthConfig] = await Promise.all([listUsers(), getAuthConfig()]);
    users.value = loadedUsers;
    authConfig.value = loadedAuthConfig;
    rememberUsers(loadedUsers);
  } catch (err) {
    await showUsersError(err instanceof Error ? err.message : "加载员工失败");
  } finally {
    loading.value = false;
  }
}

async function create() {
  clearNewUserError();
  await playCardShimmer();
  if (!(await validate(newUserForm.value, showNewUserError))) return;
  if (!newUser.company_entity) {
    await showNewUserError("请选择新员工的公司主体");
    return;
  }
  saving.value = true;
  clearNewUserError();
  success.value = "";
  try {
    const payload = { ...newUser };
    if (!passwordManagedLocally.value) delete payload.password;
    if (nameManagedBySso.value) {
      delete payload.username;
      delete payload.employee_name;
    }
    const createdUser = await createUser(payload);
    users.value = [createdUser, ...users.value];
    originalUserValues.value = new Map(originalUserValues.value).set(
      createdUser.id,
      editableUserValues(createdUser)
    );
    Object.assign(newUser, {
      username: "",
      email: "",
      password: "",
      role: "employee" as Role,
      employee_name: "",
      company_entity: ""
    });
    newPasswordVisible.value = false;
    success.value = "员工账号已创建";
  } catch (err) {
    await showNewUserError(err instanceof Error ? err.message : "创建失败");
  } finally {
    saving.value = false;
  }
}

async function saveAll() {
  if (!hasPendingChanges.value || !(await validate(usersForm.value))) return;
  saving.value = true;
  clearUsersError();
  success.value = "";
  try {
    const pendingUsers = [...usersToSave.value];
    await Promise.all(pendingUsers.map((user) => updateUser(user.id, updatePayload(user))));
    pendingUsers.forEach((user) => {
      editingPasswords[user.id] = "";
    });
    success.value = `已保存 ${pendingUsers.length} 位员工的修改`;
    await load();
  } catch (err) {
    await showUsersError(err instanceof Error ? err.message : "保存失败");
  } finally {
    saving.value = false;
  }
}

async function remove(user: AdminUser) {
  const userLabel = user.employee_name || user.email || user.username;
  if (!window.confirm(`确认永久删除账号「${userLabel}」？此操作不可恢复。已有报销或附件记录的账号不能删除。`)) return;
  saving.value = true;
  clearUsersError();
  success.value = "";
  try {
    await deleteUser(user.id);
    users.value = users.value.filter((candidate) => candidate.id !== user.id);
    const nextValues = new Map(originalUserValues.value);
    nextValues.delete(user.id);
    originalUserValues.value = nextValues;
    delete editingPasswords[user.id];
    success.value = "账号已删除";
  } catch (err) {
    await showUsersError(err instanceof Error ? err.message : "删除失败");
  } finally {
    saving.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div class="page">
    <div>
      <h1 class="page-title">人员管理</h1>
      <p class="muted mt-1">员工账号、角色和公司主体维护。</p>
    </div>

    <p v-if="success" class="rounded-control bg-state-action-soft px-3 py-2 text-sm text-state-action-ink">{{ success }}</p>

    <section
      ref="newUserCard"
      class="new-user-card error-surface t-input tool-panel relative overflow-hidden p-5"
      :class="{
        'is-shimmering': cardShimmering,
        'is-error': cardHasError,
        'is-shaking': cardErrorShaking
      }"
      @input="clearNewUserError"
    >
      <div class="mb-4">
        <h2 class="section-title">新增员工</h2>
        <p v-if="newUserError" class="t-error-msg mt-1 text-xs font-medium text-state-danger-ink">{{ newUserError }}</p>
      </div>
      <form ref="newUserForm" class="grid gap-x-4 gap-y-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6" novalidate @submit.prevent="create">
        <label v-if="authConfig && !nameManagedBySso" class="inline-edit-wrap create-field-line">
          <span class="min-w-0 flex-1">
            <input v-model="newUser.username" class="inline-edit-input" placeholder="用户名" required />
          </span>
        </label>
        <label class="inline-edit-wrap create-field-line">
          <span class="min-w-0 flex-1">
            <input v-model="newUser.email" class="inline-edit-input" placeholder="企业邮箱" required type="email" />
          </span>
        </label>
        <label v-if="authConfig && !nameManagedBySso" class="inline-edit-wrap create-field-line">
          <span class="min-w-0 flex-1">
            <input v-model="newUser.employee_name" class="inline-edit-input" placeholder="姓名" required />
          </span>
        </label>
        <div class="inline-edit-wrap create-field-line">
          <InlineAccordionSelect
            class="is-create-field min-w-0 flex-1"
            v-model="newUser.company_entity"
            :options="companyOptions"
            label="新员工的公司主体"
            placeholder="公司主体"
            @update:model-value="clearNewUserError"
          />
        </div>
        <div class="inline-edit-wrap create-field-line">
          <InlineAccordionSelect
            class="is-create-field min-w-0 flex-1"
            v-model="newUser.role"
            :options="roleOptions"
            label="新员工的角色"
            @update:model-value="clearNewUserError"
          />
        </div>
        <div v-if="passwordManagedLocally" class="inline-edit-wrap create-field-line">
          <span class="min-w-0 flex-1">
            <input
              v-model="newUser.password"
              aria-label="初始密码"
              autocomplete="new-password"
              class="inline-edit-input"
              placeholder="密码"
              required
              :type="newPasswordVisible ? 'text' : 'password'"
            />
          </span>
          <button
            class="password-visibility-button"
            type="button"
            :aria-label="newPasswordVisible ? '隐藏密码' : '显示密码'"
            @click="newPasswordVisible = !newPasswordVisible"
          >
            <EyeOff v-if="newPasswordVisible" class="h-4 w-4" />
            <Eye v-else class="h-4 w-4" />
          </button>
        </div>
        <div class="lg:col-span-6">
          <button class="primary-button" type="submit" :disabled="saving">
            <UserPlus class="h-4 w-4" />
            创建账号
          </button>
        </div>
      </form>
    </section>

    <section
      ref="usersCard"
      class="error-surface t-input tool-panel overflow-hidden"
      :class="{ 'is-error': Boolean(usersError), 'is-shaking': usersErrorShaking }"
      @input="clearUsersError"
    >
      <div class="border-b border-hairline px-4 py-3">
        <div class="flex items-center justify-between gap-3">
          <div>
            <h2 class="section-title">员工列表</h2>
            <p class="muted mt-1">{{ loading ? "正在加载..." : `共 ${users.length} 个账号` }}</p>
          </div>
          <button
            class="primary-button is-anchor h-control-lg shrink-0"
            type="button"
            :disabled="saving || !hasPendingChanges"
            @click="saveAll"
          >
            <Save class="h-4 w-4" />
            {{ saving ? "保存中..." : "保存更改" }}
          </button>
        </div>
        <p v-if="usersError" class="t-error-msg mt-2 text-xs font-medium text-state-danger-ink">{{ usersError }}</p>
      </div>

      <div v-if="loading" class="px-5 py-12 text-center text-sm text-slate-500">正在加载...</div>
      <form v-else ref="usersForm" class="overflow-x-auto" novalidate @submit.prevent="saveAll">
        <div v-if="!users.length" class="empty-state">
          <div class="empty-state-icon">
            <UserPlus class="h-6 w-6" />
          </div>
          <div>
            <div class="text-sm font-medium text-slate-700">还没有员工账号</div>
            <div class="mt-1 text-xs text-slate-500">在上方表单创建第一个员工账号。</div>
          </div>
        </div>
        <table
          v-else
          class="w-full table-fixed divide-y divide-slate-200 text-left text-sm"
          :class="nameManagedBySso ? 'min-w-[51rem]' : 'min-w-[65rem]'"
        >
          <colgroup>
            <col v-if="!nameManagedBySso" class="w-24" />
            <col class="w-48" />
            <col class="w-28" />
            <col class="w-28" />
            <col class="w-52" />
            <col class="w-28" />
            <col v-if="passwordManagedLocally" class="w-32" />
            <col class="w-24" />
          </colgroup>
          <thead class="bg-surface-soft text-xs font-medium uppercase tracking-normal text-slate-500">
            <tr>
              <th v-if="!nameManagedBySso" class="px-3 py-2.5">账号</th>
              <th class="px-3 py-2.5">企业邮箱</th>
              <th class="px-3 py-2.5">姓名</th>
              <th class="px-3 py-2.5">角色</th>
              <th class="px-3 py-2.5">绑定企业抬头</th>
              <th class="px-3 py-2.5">状态</th>
              <th v-if="passwordManagedLocally" class="px-3 py-2.5">重置密码</th>
              <th class="px-3 py-2.5">操作</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100 bg-white">
            <tr v-for="user in users" :key="user.id" class="align-top transition duration-2 ease-standard hover:bg-surface-soft">
              <td v-if="!nameManagedBySso" class="px-3 py-3 font-medium text-slate-900" :title="user.username">
                <div class="flex h-control-lg items-center truncate whitespace-nowrap">{{ user.username }}</div>
              </td>
              <td class="px-3 py-3">
                <div class="inline-edit-wrap" :class="{ 'is-modified': fieldChanged(user, 'email') }">
                  <input
                    v-model="user.email"
                    class="inline-edit-input"
                    :disabled="Boolean(user.identity_id)"
                    :required="authConfig?.mode !== 'legacy'"
                    placeholder="name@mentitrek.com"
                    type="email"
                  />
                </div>
                <p v-if="user.identity_id" class="mt-1 text-xs text-accent-ink">已绑定统一身份，不可直接修改</p>
              </td>
              <td class="px-3 py-3">
                <div v-if="nameManagedBySso" class="flex h-control-lg items-center px-1 text-slate-700">
                  {{ user.employee_name || "MentiHub 姓名暂不可用" }}
                </div>
                <div v-else class="inline-edit-wrap" :class="{ 'is-modified': fieldChanged(user, 'employee_name') }">
                  <input v-model="user.employee_name" class="inline-edit-input" required />
                </div>
              </td>
              <td class="px-3 py-3">
                <InlineAccordionSelect
                  v-model="user.role"
                  :options="roleOptions"
                  :label="`${user.employee_name || user.email || '员工'}的角色`"
                  :class="{ 'is-modified': fieldChanged(user, 'role') }"
                  @update:model-value="clearUsersError"
                />
              </td>
              <td class="px-3 py-3">
                <InlineAccordionSelect
                  v-model="user.company_entity"
                  :options="companyOptions"
                  :label="`${user.employee_name || user.email || '员工'}的公司主体`"
                  :class="{ 'is-modified': fieldChanged(user, 'company_entity') }"
                  @update:model-value="clearUsersError"
                />
              </td>
              <td class="px-3 py-3">
                <StatusToggle
                  v-model="user.is_active"
                  :label="`${user.employee_name || user.email || '员工'}账号状态`"
                  :class="{ 'is-modified': fieldChanged(user, 'is_active') }"
                  @update:model-value="clearUsersError"
                />
              </td>
              <td v-if="passwordManagedLocally" class="px-3 py-3">
                <div class="inline-edit-wrap" :class="{ 'is-modified': Boolean(editingPasswords[user.id]?.trim()) }">
                  <input v-model="editingPasswords[user.id]" autocomplete="new-password" class="inline-edit-input" placeholder="留空不改" type="password" />
                </div>
              </td>
              <td class="px-3 py-3">
                <div class="flex">
                  <button class="secondary-button btn-xs text-state-danger-ink" type="button" :disabled="saving" @click="remove(user)">
                    <Trash2 class="h-4 w-4" />
                    删除
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </form>
    </section>
  </div>
</template>

<style scoped>
.inline-edit-wrap {
  display: block;
  position: relative;
  border-radius: 0.375rem;
  transition: background-color 150ms ease-out;
}

.inline-edit-wrap.is-modified {
  background: var(--accent-soft, #eef5f4);
}

.inline-edit-wrap::after {
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  height: 1px;
  content: "";
  background: var(--accent, #34756d);
  transform: scaleX(0);
  transform-origin: left;
  transition: transform 250ms cubic-bezier(0.22, 1, 0.36, 1);
}

.inline-edit-wrap:focus-within::after {
  transform: scaleX(1);
}

.inline-edit-wrap:has(input:disabled)::after {
  display: none;
}

.inline-edit-input {
  width: 100%;
  height: 2.25rem;
  border: 0;
  border-radius: 0;
  background: transparent;
  padding: 0 0.25rem;
  color: #0f172a;
  outline: none;
}

.inline-edit-input:hover:not(:disabled) {
  background: #f8fafc;
}

.inline-edit-input:disabled {
  cursor: not-allowed;
  color: #64748b;
}

.inline-edit-input::placeholder {
  color: #94a3b8;
  font-size: 0.75rem;
  opacity: 1;
}

.create-field-line {
  display: flex;
  height: 2.5rem;
  min-width: 0;
  align-items: center;
  gap: 0.375rem;
}

.create-field-line::before {
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  height: 1px;
  content: "";
  background: #cbd5e1;
}

.password-visibility-button {
  display: grid;
  width: 2rem;
  height: 2rem;
  flex: none;
  place-items: center;
  border-radius: 0.375rem;
  color: #94a3b8;
  transition: color 150ms ease-out, background-color 150ms ease-out;
}

.password-visibility-button:hover,
.password-visibility-button:focus-visible {
  background: #f1f5f9;
  color: #475569;
  outline: none;
}

.new-user-card::after {
  position: absolute;
  z-index: 10;
  top: 0;
  right: 0;
  left: 0;
  height: 38%;
  content: "";
  pointer-events: none;
  background: linear-gradient(
    180deg,
    transparent 0%,
    rgb(16 185 129 / 0.04) 28%,
    rgb(16 185 129 / 0.24) 50%,
    rgb(16 185 129 / 0.04) 72%,
    transparent 100%
  );
  opacity: 0;
  transform: translateY(-140%) skewY(-3deg);
  will-change: transform, opacity;
}

.new-user-card.is-shimmering::after {
  animation: new-user-card-shimmer 650ms cubic-bezier(0.22, 1, 0.36, 1) both;
}

@keyframes new-user-card-shimmer {
  0% {
    opacity: 0;
    transform: translateY(-140%) skewY(-3deg);
  }
  12% { opacity: 1; }
  82% { opacity: 1; }
  100% {
    opacity: 0;
    transform: translateY(360%) skewY(-3deg);
  }
}

.new-user-card.is-error {
  border-color: #e23014;
  transition: border-color var(--revert-dur, 280ms) ease-out;
}

.new-user-card.is-shaking {
  animation: t-input-shake calc(
      var(--shake-dur-a) * 2 + var(--shake-dur-b) * 2
    ) linear;
}

.t-input {
  transition: border-color 150ms ease-out;
  will-change: transform;
}
.t-input.is-error {
  border-color: #e23014;
  transition: border-color var(--revert-dur, 280ms) ease-out;
}
.t-error-msg {
  opacity: 0;
  visibility: hidden;
  transition:
    opacity var(--revert-dur, 280ms) ease-out,
    visibility 0s linear var(--revert-dur, 280ms);
}
.error-surface.is-error .t-error-msg {
  opacity: 1;
  visibility: visible;
  transition:
    opacity var(--revert-dur, 280ms) ease-out,
    visibility 0s linear 0s;
}
.t-input.is-shaking {
  animation: t-input-shake calc(
      var(--shake-dur-a) * 2 + var(--shake-dur-b) * 2
    ) linear;
}
@keyframes t-input-shake {
  0%      { transform: translateX(0);                                 animation-timing-function: var(--shake-ease); }
  28.57%  { transform: translateX(var(--shake-distance));             animation-timing-function: var(--shake-ease); }
  57.14%  { transform: translateX(calc(var(--shake-distance) * -1)); animation-timing-function: var(--shake-ease); }
  78.57%  { transform: translateX(var(--shake-overshoot));            animation-timing-function: var(--shake-ease); }
  100%    { transform: translateX(0); }
}

@media (prefers-reduced-motion: reduce) {
  .inline-edit-wrap, .inline-edit-wrap::after { transition: none !important; }
  .t-input { animation: none !important; transform: none !important; }
  .new-user-card::after { animation: none !important; }
}
</style>
