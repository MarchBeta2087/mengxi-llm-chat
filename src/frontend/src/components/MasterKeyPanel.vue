<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ApiError, api } from '../api/client'
import type { KekStatus } from '../api/types'

const kek = ref<KekStatus | null>(null)
const remaining = ref(0)
const passphrase = ref('')
const newPassphrase = ref('')
const code = ref('')
const codes = ref<string[]>([])
const ack = ref(false)
const error = ref('')
const info = ref('')

async function load() {
  try {
    kek.value = await api.adminKek()
  } catch {
    kek.value = null
  }
  try {
    remaining.value = (await api.adminRecoveryStatus()).remaining
  } catch {
    remaining.value = 0
  }
}

async function run(action: () => Promise<unknown>, ok: string) {
  error.value = ''
  info.value = ''
  try {
    await action()
    info.value = ok
    await load()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : String(e)
  }
}

async function initialize() {
  await run(async () => {
    const status = await api.adminKekInitialize(passphrase.value)
    if (status.recovery_codes) {
      codes.value = status.recovery_codes
      ack.value = false
    }
  }, '主密钥已初始化')
  passphrase.value = ''
}

async function unlock() {
  await run(() => api.adminKekUnlock(passphrase.value), '已解锁')
  passphrase.value = ''
}

async function lock() {
  await run(() => api.adminKekLock(), '已锁定')
}

async function regenerate() {
  await run(async () => {
    codes.value = (await api.adminRecoveryRegenerate()).codes
    ack.value = false
  }, '恢复码已重新生成（旧码全部失效）')
}

async function useCode() {
  await run(async () => {
    codes.value = (await api.adminRecoveryUse(code.value, newPassphrase.value)).codes
    ack.value = false
  }, '已重置主口令（旧码全部失效）')
  code.value = ''
  newPassphrase.value = ''
}

async function copyCodes() {
  await navigator.clipboard.writeText(codes.value.join('\n'))
  info.value = '已复制到剪贴板'
}

onMounted(load)
</script>

<template>
  <div class="card">
    <h3>主密钥与恢复码（管理员）</h3>
    <p v-if="error" class="notice" role="alert">{{ error }}</p>
    <p v-if="info" class="notice ok" role="status">{{ info }}</p>

    <div class="row">
      <span>档位 / 状态</span>
      <span class="val">{{ kek ? `${kek.profile} · ${kek.state}` : '未知' }}</span>
    </div>
    <div class="row">
      <span>恢复码剩余</span>
      <span class="val">{{ remaining }}</span>
    </div>

    <div class="ops">
      <template v-if="kek?.state === 'uninitialized'">
        <input
          v-model="passphrase"
          type="password"
          aria-label="设置主口令"
          placeholder="设置主口令（≥8 位）"
        />
        <button class="btn primary small" type="button" @click="initialize">
          初始化并生成恢复码
        </button>
      </template>
      <template v-else-if="kek?.state === 'locked'">
        <input
          v-model="passphrase"
          type="password"
          aria-label="主口令"
          placeholder="主口令"
          @keyup.enter="unlock"
        />
        <button class="btn primary small" type="button" @click="unlock">解锁</button>
      </template>
      <template v-else>
        <button class="btn small" type="button" @click="lock">锁定</button>
        <button class="btn small" type="button" @click="regenerate">重新生成恢复码</button>
      </template>
    </div>

    <details class="reset">
      <summary>使用恢复码重置主口令</summary>
      <div class="ops">
        <input v-model="code" aria-label="恢复码" placeholder="XXXX-XXXX-XXXX" />
        <input
          v-model="newPassphrase"
          type="password"
          aria-label="新主口令"
          placeholder="新主口令（≥8 位）"
        />
        <button class="btn small" type="button" @click="useCode">重置</button>
      </div>
    </details>

    <div v-if="codes.length" class="codes-block">
      <p class="warn">
        ⚠ 恢复码仅展示一次，请立即离线保存；使用或重置后，旧码全部失效。
      </p>
      <div class="codes" role="group" aria-label="一次性恢复码">
        <code v-for="item in codes" :key="item">{{ item }}</code>
      </div>
      <div class="ops">
        <button class="btn small" @click="copyCodes">复制</button>
        <label class="ack"><input v-model="ack" type="checkbox" /> 我已离线保存</label>
        <button class="btn small" :disabled="!ack" @click="codes = []">隐藏</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
h3 {
  font-size: 15px;
  color: var(--xi-dark);
  margin-bottom: 12px;
}
.row {
  display: flex;
  justify-content: space-between;
  padding: 8px 0;
  border-bottom: 1px solid var(--line);
  font-size: 13px;
}
.val {
  color: var(--xi-dark);
  font-weight: 600;
}
.ops {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-top: 12px;
}
.ops input {
  padding: 7px 9px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--paper);
}
.reset {
  margin-top: 12px;
  font-size: 13px;
  color: var(--muted);
}
.reset summary {
  cursor: pointer;
}
.codes-block {
  margin-top: 14px;
}
.warn {
  background: #fff6ec;
  border: 1px solid #ecc9a8;
  color: #8a5a22;
  font-size: 12px;
  padding: 9px 13px;
  border-radius: 8px;
}
.codes {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 10px 0;
}
.codes code {
  font-family: ui-monospace, monospace;
  font-size: 13px;
  background: var(--paper);
  border: 1px dashed var(--line);
  border-radius: 6px;
  padding: 6px 10px;
}
.ack {
  font-size: 12px;
  color: var(--muted);
  display: flex;
  align-items: center;
  gap: 6px;
}
.notice.ok {
  background: #e6f0e6;
  border-color: #b7d7b7;
  color: #2f6b2f;
}
</style>
