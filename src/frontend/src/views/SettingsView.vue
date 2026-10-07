<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/client'
import { useAuthStore } from '../stores/auth'
import { useThemeStore } from '../stores/theme'
import MasterKeyPanel from '../components/MasterKeyPanel.vue'

const theme = useThemeStore()
const auth = useAuthStore()
const router = useRouter()
const audit = ref<Record<string, unknown>[]>([])

async function logout() {
  await auth.logout()
  router.push({ name: 'login' })
}

onMounted(async () => {
  audit.value = await api.myAudit(50)
})
</script>

<template>
  <div class="page">
    <h2>设置</h2>

    <div class="card">
      <h3>账户</h3>
      <div class="row">
        <span>用户名</span>
        <span>{{ auth.user?.username }}（{{ auth.user?.role }}）</span>
      </div>
      <div class="row">
        <span>会话</span>
        <button class="btn" @click="logout">退出登录</button>
      </div>
    </div>

    <div class="card">
      <h3>外观（个人偏好）</h3>
      <div class="row">
        <span>主题色</span>
        <span class="swatches">
          <button
            v-for="c in ['#2e6e63', '#3a5f8a', '#8a5a3a', '#6a4a8a']"
            :key="c"
            class="sw"
            type="button"
            :class="{ sel: theme.settings.color === c }"
            :style="{ background: c }"
            :aria-label="`主题色 ${c}`"
            :aria-pressed="theme.settings.color === c"
            @click="theme.update({ color: c })"
          />
        </span>
      </div>
      <div class="row">
        <span>深色模式</span>
        <button
          class="switch"
          type="button"
          role="switch"
          aria-label="深色模式"
          :aria-checked="theme.settings.mode === 'dark'"
          :class="{ on: theme.settings.mode === 'dark' }"
          @click="theme.update({ mode: theme.settings.mode === 'dark' ? 'light' : 'dark' })"
        />
      </div>
      <div class="row">
        <span>侧边栏宽度：{{ theme.settings.sidebarWidth }}px</span>
        <input
          type="range"
          min="200"
          max="340"
          aria-label="侧边栏宽度（像素）"
          :value="theme.settings.sidebarWidth"
          @input="theme.update({ sidebarWidth: Number(($event.target as HTMLInputElement).value) })"
        />
      </div>
    </div>

    <MasterKeyPanel v-if="auth.isAdmin()" />

    <div class="card">
      <h3>我的用量 / 审计</h3>
      <table>
        <caption class="visually-hidden">我的用量与审计记录</caption>
        <thead>
          <tr>
            <th scope="col">时间</th>
            <th scope="col">模型</th>
            <th scope="col">主机</th>
            <th scope="col">状态</th>
            <th scope="col">tokens</th>
            <th scope="col">回退</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, i) in audit" :key="i">
            <td>{{ row.created_at }}</td>
            <td>{{ row.model ?? '—' }}</td>
            <td>{{ row.base_url_host ?? '—' }}</td>
            <td>{{ row.status }}</td>
            <td>{{ row.tokens_in }}/{{ row.tokens_out }}</td>
            <td>{{ row.fallback_to_public ? '是' : '' }}</td>
          </tr>
          <tr v-if="!audit.length">
            <td colspan="6" class="empty">暂无记录</td>
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
h3 {
  font-size: 15px;
  color: var(--xi-dark);
  margin-bottom: 12px;
}
.card {
  margin-bottom: 18px;
}
.row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 0;
  border-bottom: 1px solid var(--line);
  font-size: 13px;
}
.row:last-child {
  border: none;
}
.swatches {
  display: flex;
  gap: 8px;
}
.sw {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  border: 2px solid transparent;
}
.sw.sel {
  border-color: var(--ink);
}
.kv {
  font-size: 13px;
  margin-bottom: 8px;
}
.warn {
  background: #fff6ec;
  border: 1px solid #ecc9a8;
  color: #8a5a22;
  font-size: 12px;
  padding: 9px 13px;
  border-radius: 8px;
}
.empty {
  text-align: center;
  color: var(--muted);
  padding: 16px;
}
</style>
