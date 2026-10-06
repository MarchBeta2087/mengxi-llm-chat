<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ApiError, api } from '../../api/client'
import type { ApiKey } from '../../api/types'

const keys = ref<ApiKey[]>([])
const error = ref('')
const info = ref('')
const busy = ref(false)

const form = reactive({
  provider_name: '',
  api_key: '',
  base_url: 'https://api.openai.com/v1',
  models: 'gpt-4o',
  rpm: 0,
  rpd: 0,
  tpm: 0,
  tpd: 0,
})

async function load() {
  keys.value = await api.listPublicKeys()
}

async function submit() {
  error.value = ''
  info.value = ''
  busy.value = true
  try {
    await api.createPublicKey({
      provider_name: form.provider_name,
      api_key: form.api_key,
      base_url: form.base_url,
      models: form.models
        .split(',')
        .map((m) => m.trim())
        .filter(Boolean),
      rate_limits: {
        rpm: Number(form.rpm) || 0,
        rpd: Number(form.rpd) || 0,
        tpm: Number(form.tpm) || 0,
        tpd: Number(form.tpd) || 0,
      },
    })
    form.provider_name = ''
    form.api_key = ''
    info.value = '已创建公有 Key（密文落库）'
    await load()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : String(e)
  } finally {
    busy.value = false
  }
}

async function test(key: ApiKey) {
  info.value = `测试 ${key.provider_name} 中…`
  const result = await api.testKey(key.id)
  info.value = result.ok
    ? `✅ ${key.provider_name} 连通（${result.latency_ms}ms）`
    : `❌ ${key.provider_name} 失败：${result.error ?? result.status_code}`
}

async function toggle(key: ApiKey) {
  await api.updateKey(key.id, { status: key.status === 'active' ? 'disabled' : 'active' })
  await load()
}

async function remove(key: ApiKey) {
  if (!confirm(`删除公有 Key「${key.provider_name}」？`)) return
  await api.deleteKey(key.id)
  await load()
}

onMounted(load)
</script>

<template>
  <div>
    <p v-if="error" class="notice">{{ error }}</p>
    <p v-if="info" class="notice ok">{{ info }}</p>

    <div class="card">
      <h3>公有 Key（全员可用）</h3>
      <table>
        <thead>
          <tr>
            <th>名称</th>
            <th>Key</th>
            <th>Base URL</th>
            <th>模型</th>
            <th>六维限流</th>
            <th>状态</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="key in keys" :key="key.id">
            <td>{{ key.provider_name }}</td>
            <td><code>{{ key.masked_key }}</code></td>
            <td>{{ key.base_url }}</td>
            <td>{{ key.models.join(', ') || '—' }}</td>
            <td class="rl">
              R{{ key.rate_limits.rpm || '∞' }}/{{ key.rate_limits.rpd || '∞' }} ·
              T{{ key.rate_limits.tpm || '∞' }}/{{ key.rate_limits.tpd || '∞' }}
            </td>
            <td>
              <span class="tag" :class="{ off: key.status !== 'active' }">{{ key.status }}</span>
            </td>
            <td>
              <button class="btn small" @click="test(key)">测试</button>
              <button class="btn small" @click="toggle(key)">
                {{ key.status === 'active' ? '停用' : '启用' }}
              </button>
              <button class="btn small" @click="remove(key)">删除</button>
            </td>
          </tr>
          <tr v-if="!keys.length">
            <td colspan="7" class="empty">暂无公有 Key</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="card">
      <h3>＋ 添加公有 Key</h3>
      <form class="grid" @submit.prevent="submit">
        <label class="field">展示名<input v-model="form.provider_name" required /></label>
        <label class="field">API Key<input v-model="form.api_key" type="password" required /></label>
        <label class="field">Base URL<input v-model="form.base_url" required /></label>
        <label class="field">模型（逗号分隔）<input v-model="form.models" /></label>
        <label class="field">RPM<input v-model="form.rpm" type="number" min="0" /></label>
        <label class="field">RPD<input v-model="form.rpd" type="number" min="0" /></label>
        <label class="field">TPM<input v-model="form.tpm" type="number" min="0" /></label>
        <label class="field">TPD<input v-model="form.tpd" type="number" min="0" /></label>
        <div class="full">
          <button class="btn primary" :disabled="busy">保存（经 SSRF 安全校验）</button>
        </div>
      </form>
    </div>
  </div>
</template>

<style scoped>
h3 {
  font-size: 15px;
  color: var(--xi-dark);
  margin-bottom: 12px;
}
.card {
  margin-bottom: 18px;
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
}
.full {
  grid-column: 1 / -1;
}
.rl {
  font-size: 12px;
  color: var(--muted);
}
.empty {
  text-align: center;
  color: var(--muted);
  padding: 16px;
}
.notice.ok {
  background: #e6f0e6;
  border-color: #b7d7b7;
  color: #2f6b2f;
}
code {
  font-family: ui-monospace, monospace;
}
</style>
