import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { useThemeStore } from './theme'

describe('theme store', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('更新设置并应用到 CSS 变量', async () => {
    const store = useThemeStore()
    store.update({ color: '#123456', sidebarWidth: 300, fontSize: 16 })
    await nextTick()

    const root = document.documentElement.style
    expect(root.getPropertyValue('--xi')).toBe('#123456')
    expect(root.getPropertyValue('--sidebar-width')).toBe('300px')
    expect(root.getPropertyValue('--font-size')).toBe('16px')
  })

  it('深色模式写入 data-theme 并持久化', async () => {
    const store = useThemeStore()
    store.update({ mode: 'dark' })
    await nextTick()

    expect(document.documentElement.dataset.theme).toBe('dark')
    const saved = JSON.parse(localStorage.getItem('mengxi.theme') ?? '{}')
    expect(saved.mode).toBe('dark')
  })

  it('默认浅色', () => {
    const store = useThemeStore()
    expect(store.settings.mode).toBe('light')
    expect(store.dark).toBe(false)
  })

  it('跟随系统模式读取 matchMedia', () => {
    vi.stubGlobal('matchMedia', (query: string) => ({
      matches: true,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }))
    const store = useThemeStore()
    store.update({ mode: 'system' })
    expect(store.dark).toBe(true)
  })
})
