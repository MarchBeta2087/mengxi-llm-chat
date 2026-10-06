import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api/client'
import type { User } from '../api/types'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const ready = ref(false)

  async function refresh() {
    try {
      user.value = await api.me()
    } catch {
      user.value = null
    } finally {
      ready.value = true
    }
  }

  async function login(username: string, password: string) {
    user.value = await api.login(username, password)
  }

  async function register(username: string, password: string) {
    user.value = await api.register(username, password)
  }

  async function logout() {
    await api.logout()
    user.value = null
  }

  const isAdmin = () => user.value?.role === 'admin'

  return { user, ready, refresh, login, register, logout, isAdmin }
})
