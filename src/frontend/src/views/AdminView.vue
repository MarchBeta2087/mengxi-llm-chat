<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ApiError, api } from '../api/client'

interface AdminUser {
  id: string
  username: string
  role: string
  status: string
  daily_quota_tokens: number
  group_id: string | null
}
interface AdminGroup {
  id: string
  name: string
  daily_quota_tokens: number
}

const tab = ref<'users' | 'groups' | 'audit'>('users')
const users = ref<AdminUser[]>([])
const groups = ref<AdminGroup[]>([])
const audit = ref<Record<string, unknown>[]>([])
const newGroup = ref('')
const fallbackOnly = ref(false)
const error = ref('')

async function loadUsers() {
  users.value = (await api.adminUsers()) as unknown as AdminUser[]
}
async function loadGroups() {
  groups.value = (await api.adminGroups()) as unknown as AdminGroup[]
}
async function loadAudit() {
  audit.value = await api.adminAudit(fallbackOnly.value ? '?fallback_only=true' : '')
}

async function setQuota(user: AdminUser) {
  const value = prompt(`设置 ${user.username} 的每日 Token 配额（0=不限）`, String(user.daily_quota_tokens))
  if (value === null) return
  await api.adminUpdateUser(user.id, { daily_quota_tokens: Number(value) || 0 })
  await loadUsers()
}

async function setStatus(user: AdminUser) {
  await api.adminUpdateUser(user.id, {
    status: user.status === 'active' ? 'banned' : 'active',
  })
  await loadUsers()
}

async function assignGroup(user: AdminUser, groupId: string) {
  try {
    await api.adminUpdateUser(user.id, { group_id: groupId || null })
    await loadUsers()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : String(e)
  }
}

async function createGroup() {
  if (!newGroup.value.trim()) return
  try {
    await api.adminCreateGroup(newGroup.value.trim())
    newGroup.value = ''
    await loadGroups()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : String(e)
  }
}

onMounted(async () => {
  await Promise.all([loadUsers(), loadGroups(), loadAudit()])
})
</script>

<template>
  <div class="page">
    <h2>管理后台</h2>
    <div class="tabs">
      <button :class="{ on: tab === 'users' }" @click="tab = 'users'">用户</button>
      <button :class="{ on: tab === 'groups' }" @click="tab = 'groups'">用户组</button>
      <button :class="{ on: tab === 'audit' }" @click="tab = 'audit'">审计</button>
    </div>
    <p v-if="error" class="notice">{{ error }}</p>

    <div v-if="tab === 'users'" class="card">
      <table>
        <thead>
          <tr>
            <th>用户名</th>
            <th>角色</th>
            <th>状态</th>
            <th>日配额</th>
            <th>用户组</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="user in users" :key="user.id">
            <td>{{ user.username }}</td>
            <td>{{ user.role }}</td>
            <td>
              <span class="tag" :class="{ off: user.status !== 'active' }">{{ user.status }}</span>
            </td>
            <td>{{ user.daily_quota_tokens || '不限' }}</td>
            <td>
              <select :value="user.group_id ?? ''" @change="assignGroup(user, ($event.target as HTMLSelectElement).value)">
                <option value="">未分组</option>
                <option v-for="group in groups" :key="group.id" :value="group.id">
                  {{ group.name }}
                </option>
              </select>
            </td>
            <td>
              <button class="btn small" @click="setQuota(user)">改配额</button>
              <button class="btn small" @click="setStatus(user)">
                {{ user.status === 'active' ? '封禁' : '解封' }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="tab === 'groups'" class="card">
      <div class="create">
        <input v-model="newGroup" placeholder="新用户组名称" />
        <button class="btn primary small" @click="createGroup">创建</button>
      </div>
      <table>
        <thead>
          <tr>
            <th>名称</th>
            <th>日配额</th>
            <th>ID</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="group in groups" :key="group.id">
            <td>{{ group.name }}</td>
            <td>{{ group.daily_quota_tokens || '不限' }}</td>
            <td><code>{{ group.id }}</code></td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="tab === 'audit'" class="card">
      <label class="filter">
        <input v-model="fallbackOnly" type="checkbox" @change="loadAudit" /> 仅看回退记录
      </label>
      <table>
        <thead>
          <tr>
            <th>时间</th>
            <th>用户</th>
            <th>Key 类型</th>
            <th>模型</th>
            <th>状态</th>
            <th>tokens</th>
            <th>回退</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, i) in audit" :key="i">
            <td>{{ row.created_at }}</td>
            <td>{{ row.user_id ?? '—' }}</td>
            <td>{{ row.key_type ?? '—' }}</td>
            <td>{{ row.model ?? '—' }}</td>
            <td>{{ row.status }}</td>
            <td>{{ row.tokens_in }}/{{ row.tokens_out }}</td>
            <td>{{ row.fallback_to_public ? '是' : '' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.page {
  padding: 24px 5vw;
  height: 100vh;
  overflow-y: auto;
}
h2 {
  font-family: 'Songti SC', serif;
  color: var(--xi-dark);
}
.tabs {
  display: flex;
  gap: 6px;
  margin: 14px 0;
}
.tabs button {
  padding: 7px 18px;
  border: 1px solid var(--line);
  background: var(--surface);
  border-radius: 8px;
}
.tabs button.on {
  background: var(--xi);
  color: #fff;
  border-color: var(--xi);
}
.create {
  display: flex;
  gap: 8px;
  margin-bottom: 14px;
}
.create input {
  padding: 7px 10px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--paper);
}
.filter {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 10px;
}
select {
  padding: 4px 6px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--paper);
}
code {
  font-family: ui-monospace, monospace;
  font-size: 11px;
}
</style>
