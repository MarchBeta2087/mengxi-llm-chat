import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from './stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('./views/LoginView.vue'),
      meta: { public: true },
    },
    {
      path: '/',
      component: () => import('./components/AppLayout.vue'),
      children: [
        { path: '', name: 'chat', component: () => import('./views/ChatView.vue') },
        { path: 'keys', name: 'keys', component: () => import('./views/KeysView.vue') },
        { path: 'plugins', name: 'plugins', component: () => import('./views/PluginsView.vue') },
        { path: 'settings', name: 'settings', component: () => import('./views/SettingsView.vue') },
        {
          path: 'admin',
          name: 'admin',
          component: () => import('./views/AdminView.vue'),
          meta: { admin: true },
        },
      ],
    },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (!auth.ready) await auth.refresh()
  if (to.meta.public) return true
  if (!auth.user) return { name: 'login', query: { redirect: to.fullPath } }
  if (to.meta.admin && auth.user.role !== 'admin') return { name: 'chat' }
  return true
})

export default router
