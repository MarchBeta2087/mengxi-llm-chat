import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import AdminPlugins from './AdminPlugins.vue'
import { api } from '../../api/client'
import type { AdminPlugin } from '../../api/types'

const BUILTIN = {
  name: 'echo',
  version: '1.0.0',
  description: '回显插件',
  type: 'optional' as const,
  entry: 'main.py',
  permissions: [],
  default_state: 'disabled' as const,
  runtime: { timeout_ms: 5000, memory_mb: 64, cpu_seconds: 2 },
}

describe('AdminPlugins', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('展示内置插件市场并安装/查看详情', async () => {
    vi.spyOn(api, 'adminListPlugins').mockResolvedValue([])
    vi.spyOn(api, 'adminGroups').mockResolvedValue([])
    vi.spyOn(api, 'adminBuiltinPlugins').mockResolvedValue([BUILTIN])
    const install = vi
      .spyOn(api, 'adminInstallBuiltin')
      .mockResolvedValue({} as unknown as AdminPlugin)

    const wrapper = mount(AdminPlugins)
    await flushPromises()
    expect(wrapper.text()).toContain('echo')

    await wrapper.findAll('button').find((b) => b.text() === '详情')!.trigger('click')
    expect(wrapper.find('pre').exists()).toBe(true)

    await wrapper.findAll('button').find((b) => b.text() === '安装')!.trigger('click')
    await flushPromises()
    expect(install).toHaveBeenCalledWith('echo')
  })

  it('安装自定义插件并调整类型', async () => {
    const plugin = {
      id: 'p1',
      name: 'custom',
      version: '1.0.0',
      description: '',
      type: 'optional',
      default_state: 'disabled',
      status: 'active',
      permissions: [],
      runtime: {},
    } as AdminPlugin
    vi.spyOn(api, 'adminListPlugins').mockResolvedValue([plugin])
    vi.spyOn(api, 'adminGroups').mockResolvedValue([])
    vi.spyOn(api, 'adminBuiltinPlugins').mockResolvedValue([])
    const install = vi
      .spyOn(api, 'adminInstallPlugin')
      .mockResolvedValue({} as unknown as AdminPlugin)
    const patch = vi.spyOn(api, 'adminUpdatePlugin').mockResolvedValue(plugin)

    const wrapper = mount(AdminPlugins)
    await flushPromises()

    // 路径：自定义安装
    await wrapper.find('textarea').setValue('{}')
    await wrapper.findAll('button').find((b) => b.text() === '安装 / 更新')!.trigger('click')
    await flushPromises()
    expect(install).toHaveBeenCalled()

    // 类型改为全局
    await wrapper.findAll('tbody select')[0].setValue('global')
    expect(patch).toHaveBeenCalledWith('p1', { type: 'global' })
  })
})
