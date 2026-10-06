import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import ThemePanel from './ThemePanel.vue'
import { useThemeStore } from '../stores/theme'

describe('ThemePanel', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
  })

  it('关闭按钮与主题色切换', async () => {
    const store = useThemeStore()
    store.panelOpen = true
    const wrapper = mount(ThemePanel)

    const swatches = wrapper.findAll('.sw')
    await swatches[1].trigger('click')
    expect(store.settings.color).toBe('#3a5f8a')

    await wrapper.find('header button').trigger('click')
    expect(store.panelOpen).toBe(false)
  })

  it('模式与滑杆更新设置', async () => {
    const store = useThemeStore()
    store.panelOpen = true
    const wrapper = mount(ThemePanel)

    const select = wrapper.find('select')
    await select.setValue('dark')
    expect(store.settings.mode).toBe('dark')

    const ranges = wrapper.findAll('input[type=range]')
    await ranges[0].setValue('320')
    expect(store.settings.sidebarWidth).toBe(320)
    await ranges[1].setValue('2')
    expect(store.settings.density).toBe(2)
    await ranges[2].setValue('16')
    expect(store.settings.fontSize).toBe(16)
  })

  it('关闭状态不渲染面板', () => {
    const store = useThemeStore()
    store.panelOpen = false
    const wrapper = mount(ThemePanel)
    expect(wrapper.find('.panel').exists()).toBe(false)
  })
})
