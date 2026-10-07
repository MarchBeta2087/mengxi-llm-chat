<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ApiError, api } from '../api/client'
import type { Plugin } from '../api/types'

const plugins = ref<Plugin[]>([])
const error = ref('')

const globals = computed(() => plugins.value.filter((p) => p.type === 'global'))
const optionals = computed(() => plugins.value.filter((p) => p.type === 'optional'))

const sourceLabel: Record<string, string> = {
  global: '全局强制',
  group: '用户组设定',
  user: '个人设置',
  default: '默认状态',
}

async function load() {
  plugins.value = await api.listPlugins()
}

async function toggle(plugin: Plugin) {
  error.value = ''
  try {
    plugins.value = await api.togglePlugin(plugin.id, !plugin.enabled)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : String(e)
  }
}

onMounted(load)
</script>

<template>
  <div class="page">
    <h2>插件</h2>
    <p class="hint">
      生效优先级：全局插件（强制）&gt; 用户组配置 &gt; 个人设置 &gt; 默认状态
    </p>
    <p v-if="error" class="notice" role="alert">{{ error }}</p>

    <h3><span aria-hidden="true">🔴</span> 全局插件（强制生效，不可禁用）</h3>
    <div class="grid">
      <div v-for="plugin in globals" :key="plugin.id" class="card plugin">
        <header>
          <strong>{{ plugin.name }}</strong>
          <span class="tag priv">全局</span>
        </header>
        <p class="desc">{{ plugin.description }}</p>
        <div class="perm">权限：{{ plugin.permissions.join(', ') || '无网络 / 无文件' }}</div>
        <div class="foot">
          <span class="src">{{ sourceLabel[plugin.state_source] }}</span>
          <button
            class="switch on lock"
            type="button"
            role="switch"
            aria-checked="true"
            :aria-label="`${plugin.name}（全局强制，不可禁用）`"
            disabled
          />
        </div>
      </div>
      <p v-if="!globals.length" class="empty">暂无全局插件。</p>
    </div>

    <h3><span aria-hidden="true">🟢</span> 可选插件（用户可启停）</h3>
    <div class="grid">
      <div v-for="plugin in optionals" :key="plugin.id" class="card plugin">
        <header>
          <strong>{{ plugin.name }}</strong>
          <span class="tag">可选</span>
        </header>
        <p class="desc">{{ plugin.description }}</p>
        <div class="perm">权限：{{ plugin.permissions.join(', ') || '无网络 / 无文件' }}</div>
        <div class="foot">
          <span class="src">{{ sourceLabel[plugin.state_source] }}</span>
          <button
            class="switch"
            type="button"
            role="switch"
            :aria-checked="plugin.enabled"
            :aria-label="`${plugin.enabled ? '停用' : '启用'} ${plugin.name}`"
            :class="{ on: plugin.enabled, lock: plugin.state_source === 'group' }"
            :disabled="plugin.state_source === 'group'"
            @click="toggle(plugin)"
          />
        </div>
      </div>
      <p v-if="!optionals.length" class="empty">暂无可选插件。</p>
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
h3 {
  font-size: 14px;
  color: var(--xi-dark);
  margin: 22px 0 12px;
}
.hint {
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 10px;
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
}
.plugin header {
  display: flex;
  align-items: center;
  gap: 8px;
}
.desc {
  font-size: 12px;
  color: var(--muted);
  margin: 8px 0 12px;
  line-height: 1.6;
}
.perm {
  font-size: 11px;
  color: var(--muted);
  background: var(--paper);
  border-radius: 6px;
  padding: 6px 9px;
  margin-bottom: 12px;
}
.foot {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.src {
  font-size: 11px;
  color: var(--muted);
}
.empty {
  color: var(--muted);
  font-size: 13px;
}
</style>
