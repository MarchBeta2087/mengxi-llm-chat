<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ApiError, api } from '../../api/client'

interface AuditRow {
  created_at: string
  user_id: string | null
  key_type: string | null
  model: string | null
  status: number
  tokens_in: number
  tokens_out: number
  fallback_to_public: boolean
}

const rows = ref<AuditRow[]>([])
const fallbackOnly = ref(false)
const status = ref('')
const error = ref('')

async function load() {
  error.value = ''
  const params = new URLSearchParams()
  if (fallbackOnly.value) params.set('fallback_only', 'true')
  if (status.value) params.set('status', status.value)
  const qs = params.toString()
  try {
    rows.value = (await api.adminAudit(qs ? `?${qs}` : '')) as unknown as AuditRow[]
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : String(e)
  }
}

onMounted(load)
</script>

<template>
  <div class="card">
    <div class="filters">
      <label><input v-model="fallbackOnly" type="checkbox" @change="load" /> 仅看回退记录</label>
      <label>
        状态
        <select v-model="status" @change="load">
          <option value="">全部</option>
          <option value="200">200</option>
          <option value="429">429</option>
          <option value="502">502</option>
        </select>
      </label>
      <button class="btn small" @click="load">刷新</button>
    </div>
    <p v-if="error" class="notice">{{ error }}</p>
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
        <tr v-for="(row, i) in rows" :key="i">
          <td>{{ row.created_at }}</td>
          <td>{{ row.user_id ?? '—' }}</td>
          <td>{{ row.key_type ?? '—' }}</td>
          <td>{{ row.model ?? '—' }}</td>
          <td>{{ row.status }}</td>
          <td>{{ row.tokens_in }}/{{ row.tokens_out }}</td>
          <td>{{ row.fallback_to_public ? '是' : '' }}</td>
        </tr>
        <tr v-if="!rows.length">
          <td colspan="7" class="empty">暂无记录</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.filters {
  display: flex;
  align-items: center;
  gap: 16px;
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 12px;
}
.filters label {
  display: flex;
  align-items: center;
  gap: 6px;
}
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
