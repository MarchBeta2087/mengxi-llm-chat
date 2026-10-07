<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ApiError, api } from '../api/client'
import type { ApiKey } from '../api/types'

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
})

async function load() {
  keys.value = await api.listKeys('private')
}

async function submit() {
  error.value = ''
  info.value = ''
  busy.value = true
  try {
    await api.createKey({
      provider_name: form.provider_name,
      api_key: form.api_key,
      base_url: form.base_url,
      models: form.models
        .split(',')
        .map((m) => m.trim())
        .filter(Boolean),
      rate_limits: { rpm: Number(form.rpm) || 0, rpd: Number(form.rpd) || 0 },
    })
    form.provider_name = ''
    form.api_key = ''
    info.value = '已保存（密文落库）'
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
  if (!confirm(`删除密钥「${key.provider_name}」？`)) return
  await api.deleteKey(key.id)
  await load()
}

onMounted(load)
</script>

<template>
  <div class="page">
    <h2>我的 Key</h2>
    <p class="hint">所有 Key 以 AES-256-GCM 加密存储，界面仅显示脱敏形式。</p>

    <p v-if="error" class="notice" role="alert">{{ error }}</p>
    <p v-if="info" class="notice ok" role="status">{{ info }}</p>

    <div class="card">
      <table>
        <caption class="visually-hidden">我的私有 API Key 列表</caption>
        <thead>
          <tr>
            <th scope="col">名称</th>
            <th scope="col">Key</th>
            <th scope="col">Base URL</th>
            <th scope="col">模型</th>
            <th scope="col">状态</th>
            <th scope="col">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="key in keys" :key="key.id">
            <td>{{ key.provider_name }}</td>
            <td><code>{{ key.masked_key }}</code></td>
            <td>{{ key.base_url }}</td>
            <td>{{ key.models.join(', ') || '—' }}</td>
            <td>
              <span class="tag" :class="{ off: key.status !== 'active' }">{{ key.status }}</span>
            </td>
            <td>
              <button class="btn small" type="button" :aria-label="`测试 ${key.provider_name}`" @click="test(key)">
                测试
              </button>
              <button
                class="btn small"
                type="button"
                :aria-label="`${key.status === 'active' ? '停用' : '启用'} ${key.provider_name}`"
                @click="toggle(key)"
              >
                {{ key.status === 'active' ? '停用' : '启用' }}
              </button>
              <button
                class="btn small"
                type="button"
                :aria-label="`删除 ${key.provider_name}`"
                @click="remove(key)"
              >
                删除
              </button>
            </td>
          </tr>
          <tr v-if="!keys.length">
            <td colspan="6" class="empty">还没有密钥，先在下方添加一个吧。</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="card">
      <h3>＋ 添加 Key</h3>
      <form class="grid" @submit.prevent="submit">
        <label class="field">展示名<input v-model="form.provider_name" required /></label>
        <label class="field">API Key<input v-model="form.api_key" type="password" required /></label>
        <label class="field">Base URL<input v-model="form.base_url" required /></label>
        <label class="field">模型（逗号分隔）<input v-model="form.models" /></label>
        <label class="field">RPM<input v-model="form.rpm" type="number" min="0" /></label>
        <label class="field">RPD<input v-model="form.rpd" type="number" min="0" /></label>
        <div class="full">
          <button class="btn primary" :disabled="busy">保存（经 SSRF 安全校验）</button>
        </div>
      </form>
      <p class="hint">
        提示：内网、回环、链路本地地址（如 169.254.169.254）会被拒绝，重定向逐跳检查。
      </p>
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
  margin-bottom: 4px;
}
h3 {
  font-size: 15px;
  margin-bottom: 12px;
  color: var(--xi-dark);
}
.hint {
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 12px;
}
.notice.ok {
  background: #e6f0e6;
  border-color: #b7d7b7;
  color: #2f6b2f;
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
.empty {
  text-align: center;
  color: var(--muted);
  padding: 20px;
}
code {
  font-family: ui-monospace, monospace;
}
</style>
