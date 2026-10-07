<script setup lang="ts">
import { RouterLink, RouterView, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { useThemeStore } from '../stores/theme'
import ThemePanel from './ThemePanel.vue'

const auth = useAuthStore()
const theme = useThemeStore()
const router = useRouter()

async function logout() {
  await auth.logout()
  router.push({ name: 'login' })
}
</script>

<template>
  <div class="shell">
    <nav class="rail">
      <div class="brand">
        <h1>梦溪畅谈</h1>
        <p>mengxi-llm-chat</p>
      </div>
      <RouterLink to="/" class="nav-link">💬 聊天</RouterLink>
      <RouterLink to="/keys" class="nav-link">🔑 我的 Key</RouterLink>
      <RouterLink to="/plugins" class="nav-link">🧩 插件</RouterLink>
      <RouterLink to="/settings" class="nav-link">⚙ 设置</RouterLink>
      <RouterLink to="/about" class="nav-link">ℹ 关于</RouterLink>
      <RouterLink v-if="auth.isAdmin()" to="/admin" class="nav-link">🛡 管理后台</RouterLink>
      <div class="spacer" />
      <button class="nav-link" @click="theme.panelOpen = !theme.panelOpen">🎨 外观</button>
      <div class="who">
        <span class="uname">{{ auth.user?.username }}</span>
        <span class="role">{{ auth.user?.role }}</span>
      </div>
      <button class="nav-link logout" @click="logout">🚪 退出登录</button>
    </nav>
    <main class="content">
      <RouterView />
    </main>
    <ThemePanel />
  </div>
</template>

<style scoped>
.shell {
  display: flex;
  height: 100vh;
}
.rail {
  width: 190px;
  flex-shrink: 0;
  background: var(--surface);
  border-right: 1px solid var(--line);
  display: flex;
  flex-direction: column;
  padding: 14px 10px;
  gap: 4px;
}
.brand {
  padding: 6px 8px 14px;
}
.brand h1 {
  font-family: 'Songti SC', serif;
  font-size: 19px;
  letter-spacing: 2px;
  color: var(--xi-dark);
}
.brand p {
  font-size: 10px;
  color: var(--muted);
}
.nav-link {
  display: block;
  padding: 9px 12px;
  border-radius: 8px;
  font-size: 13px;
  color: var(--ink);
  background: none;
  border: none;
  text-align: left;
  width: 100%;
}
.nav-link:hover {
  background: var(--paper);
}
.nav-link.router-link-exact-active {
  background: var(--bubble-user);
  color: var(--xi-dark);
  font-weight: 600;
}
.spacer {
  flex: 1;
}
.who {
  font-size: 12px;
  color: var(--muted);
  padding: 8px 12px 2px;
  display: flex;
  justify-content: space-between;
}
.role {
  color: var(--accent);
}
.uname {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.logout {
  color: var(--accent);
}
.content {
  flex: 1;
  min-width: 0;
  overflow: hidden;
}
</style>
