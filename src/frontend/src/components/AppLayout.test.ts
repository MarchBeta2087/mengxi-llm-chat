import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import AppLayout from './AppLayout.vue'
import { api } from '../api/client'
import { useAuthStore } from '../stores/auth'

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<div />' } },
      { path: '/login', name: 'login', component: { template: '<div />' } },
      { path: '/keys', component: { template: '<div />' } },
      { path: '/plugins', component: { template: '<div />' } },
      { path: '/settings', component: { template: '<div />' } },
      { path: '/about', component: { template: '<div />' } },
      { path: '/admin', component: { template: '<div />' } },
    ],
  })
}

async function mountLayout(role: 'user' | 'admin') {
  const pinia = createPinia()
  setActivePinia(pinia)
  const auth = useAuthStore()
  auth.user = { id: 'u1', username: 'alice', role, status: 'active' }
  const router = makeRouter()
  await router.push('/')
  await router.isReady()
  const wrapper = mount(AppLayout, {
    global: { plugins: [pinia, router] },
  })
  return { wrapper, auth, router }
}

describe('AppLayout', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('普通用户无管理入口，可退出登录', async () => {
    vi.spyOn(api, 'logout').mockResolvedValue(null)
    const { wrapper, auth } = await mountLayout('user')

    expect(wrapper.text()).toContain('关于')
    expect(wrapper.text()).not.toContain('管理后台')
    await wrapper.find('.logout').trigger('click')
    await flushPromises()

    expect(api.logout).toHaveBeenCalled()
    expect(auth.user).toBeNull()
  })

  it('管理员显示管理后台入口', async () => {
    const { wrapper } = await mountLayout('admin')
    expect(wrapper.text()).toContain('管理后台')
  })
})
