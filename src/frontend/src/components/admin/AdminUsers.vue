<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ApiError, api } from '../../api/client'

interface AdminUser {
  id: string
  username: string
  role: string
  status: string
  daily_quota_tokens: number
  group_id: string | null
}
interface Group {
  id: string
  name: string
}

const users = ref<AdminUser[]>([])
const groups = ref<Group[]>([])
const error = ref('')

async function load() {
  users.value = (await api.adminUsers()) as unknown as AdminUser[]
  groups.value = (await api.adminGroups()) as unknown as Group[]
}

async function setQuota(user: AdminUser) {
  const value = prompt(
    `设置 ${user.username} 的每日 Token 配额（0 = 不限）`,
    String(user.daily_quota_tokens),
  )
  if (value === null) return
  await api.adminUpdateUser(user.id, { daily_quota_tokens: Number(value) || 0 })
  await load()
}

async function toggleStatus(user: AdminUser) {
  await api.adminUpdateUser(user.id, {
    status: user.status === 'active' ? 'banned' : 'active',
  })
  await load()
}

async function assignGroup(user: AdminUser, groupId: string) {
  error.value = ''
  try {
    await api.adminUpdateUser(user.id, { group_id: groupId || null })
    await load()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : String(e)
  }
}

onMounted(load)
</script>

<template>
  <div class="card">
    <p v-if="error" class="notice">{{ error }}</p>
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
            <select
              :value="user.group_id ?? ''"
              @change="assignGroup(user, ($event.target as HTMLSelectElement).value)"
            >
              <option value="">未分组</option>
              <option v-for="group in groups" :key="group.id" :value="group.id">
                {{ group.name }}
              </option>
            </select>
          </td>
          <td>
            <button class="btn small" @click="setQuota(user)">改配额</button>
            <button class="btn small" @click="toggleStatus(user)">
              {{ user.status === 'active' ? '封禁' : '解封' }}
            </button>
          </td>
        </tr>
        <tr v-if="!users.length">
          <td colspan="6" class="empty">暂无用户</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
select {
  padding: 4px 6px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--paper);
}
.empty {
  text-align: center;
  color: var(--muted);
  padding: 16px;
}
</style>
