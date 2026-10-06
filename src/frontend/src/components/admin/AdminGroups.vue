<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ApiError, api } from '../../api/client'

interface Group {
  id: string
  name: string
  daily_quota_tokens: number
}

const groups = ref<Group[]>([])
const newName = ref('')
const newQuota = ref(0)
const error = ref('')

async function load() {
  groups.value = (await api.adminGroups()) as unknown as Group[]
}

async function create() {
  error.value = ''
  if (!newName.value.trim()) return
  try {
    await api.adminCreateGroup(newName.value.trim(), Number(newQuota.value) || 0)
    newName.value = ''
    newQuota.value = 0
    await load()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : String(e)
  }
}

onMounted(load)
</script>

<template>
  <div class="card">
    <div class="create">
      <input v-model="newName" placeholder="新用户组名称" />
      <input
        v-model="newQuota"
        type="number"
        min="0"
        placeholder="组日配额（0=不限）"
        class="quota"
      />
      <button class="btn primary small" @click="create">创建</button>
    </div>
    <p v-if="error" class="notice">{{ error }}</p>
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
        <tr v-if="!groups.length">
          <td colspan="3" class="empty">暂无用户组</td>
        </tr>
      </tbody>
    </table>
    <p class="hint">用户组配额与成员分组请到「用户」标签页设置；组插件策略见「插件」标签页。</p>
  </div>
</template>

<style scoped>
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
.quota {
  width: 160px;
}
.hint {
  font-size: 12px;
  color: var(--muted);
  margin-top: 10px;
}
.empty {
  text-align: center;
  color: var(--muted);
  padding: 16px;
}
code {
  font-family: ui-monospace, monospace;
  font-size: 11px;
}
</style>
