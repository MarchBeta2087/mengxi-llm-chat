import { defineStore } from 'pinia'
import { computed, ref, watchEffect } from 'vue'

export interface ThemeSettings {
  color: string
  mode: 'light' | 'dark' | 'system'
  sidebarWidth: number
  density: number
  fontSize: number
}

const STORAGE_KEY = 'mengxi.theme'
const DEFAULTS: ThemeSettings = {
  color: '#2e6e63',
  mode: 'light',
  sidebarWidth: 260,
  density: 2,
  fontSize: 14,
}

function load(): ThemeSettings {
  try {
    return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}') }
  } catch {
    return { ...DEFAULTS }
  }
}

export const useThemeStore = defineStore('theme', () => {
  const settings = ref<ThemeSettings>(load())
  const panelOpen = ref(false)

  const dark = computed(() => {
    if (settings.value.mode === 'system') {
      return window.matchMedia('(prefers-color-scheme: dark)').matches
    }
    return settings.value.mode === 'dark'
  })

  function apply() {
    const root = document.documentElement
    root.style.setProperty('--xi', settings.value.color)
    root.style.setProperty('--sidebar-width', `${settings.value.sidebarWidth}px`)
    root.style.setProperty('--font-size', `${settings.value.fontSize}px`)
    root.style.setProperty('--density', String(settings.value.density))
    root.dataset.theme = dark.value ? 'dark' : 'light'
  }

  watchEffect(() => {
    apply()
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings.value))
  })

  function update(patch: Partial<ThemeSettings>) {
    settings.value = { ...settings.value, ...patch }
  }

  return { settings, panelOpen, dark, update, apply }
})
