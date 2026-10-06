import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import AdminGroups from './AdminGroups.vue'
import { api } from '../../api/client'

describe('AdminGroups', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('列出并可创建用户组', async () => {
    vi.spyOn(api, 'adminGroups').mockResolvedValue([
      { id: 'g1', name: '研发组', daily_quota_tokens: 100 },
    ])
    const create = vi.spyOn(api, 'adminCreateGroup').mockResolvedValue({})

    const wrapper = mount(AdminGroups)
    await flushPromises()
    expect(wrapper.text()).toContain('研发组')

    await wrapper.find('.create input').setValue('新组')
    await wrapper.find('.create button').trigger('click')
    await flushPromises()
    expect(create).toHaveBeenCalledWith('新组', 0)
  })

  it('可改配额与改名', async () => {
    vi.spyOn(api, 'adminGroups').mockResolvedValue([
      { id: 'g1', name: '研发组', daily_quota_tokens: 100 },
    ])
    const update = vi.spyOn(api, 'adminUpdateGroup').mockResolvedValue({})

    const wrapper = mount(AdminGroups)
    await flushPromises()

    vi.spyOn(window, 'prompt').mockReturnValue('500')
    await wrapper.findAll('tbody button')[0].trigger('click')
    expect(update).toHaveBeenCalledWith('g1', { daily_quota_tokens: 500 })

    vi.spyOn(window, 'prompt').mockReturnValue('改名后')
    await wrapper.findAll('tbody button')[1].trigger('click')
    expect(update).toHaveBeenCalledWith('g1', { name: '改名后' })
  })
})
