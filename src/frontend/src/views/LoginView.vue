<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ApiError } from '../api/client'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

const mode = ref<'login' | 'register'>('login')
const username = ref('')
const password = ref('')
const error = ref('')
const busy = ref(false)

async function submit() {
  error.value = ''
  busy.value = true
  try {
    if (mode.value === 'login') await auth.login(username.value, password.value)
    else await auth.register(username.value, password.value)
    router.push((route.query.redirect as string) || '/')
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : String(e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="login">
    <div class="card box">
      <h1>梦溪畅谈</h1>
      <p class="sub">可自部署的 LLM 聊天服务</p>

      <div class="tabs">
        <button :class="{ on: mode === 'login' }" @click="mode = 'login'">登录</button>
        <button :class="{ on: mode === 'register' }" @click="mode = 'register'">注册</button>
      </div>

      <form @submit.prevent="submit">
        <label class="field">
          用户名
          <input v-model="username" autocomplete="username" required minlength="3" />
        </label>
        <label class="field">
          密码
          <input
            v-model="password"
            type="password"
            autocomplete="current-password"
            required
            minlength="8"
          />
        </label>
        <p v-if="error" class="notice">{{ error }}</p>
        <button class="btn primary wide" :disabled="busy">
          {{ busy ? '处理中…' : mode === 'login' ? '登录' : '注册并登录' }}
        </button>
      </form>
    </div>
  </div>
</template>

<style scoped>
.login {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100vh;
}
.box {
  width: 340px;
  padding: 28px;
}
h1 {
  font-family: 'Songti SC', serif;
  color: var(--xi-dark);
  letter-spacing: 2px;
}
.sub {
  font-size: 12px;
  color: var(--muted);
  margin: 4px 0 18px;
}
.tabs {
  display: flex;
  gap: 6px;
  margin-bottom: 16px;
}
.tabs button {
  flex: 1;
  padding: 8px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--paper);
}
.tabs button.on {
  background: var(--xi);
  color: #fff;
  border-color: var(--xi);
}
form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.wide {
  width: 100%;
  padding: 9px;
}
</style>
