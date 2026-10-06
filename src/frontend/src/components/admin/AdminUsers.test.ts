import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import AdminUsers from './AdminUsers.vue'
import { api } from '../../api/client'

describe('AdminUsers', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('列出用户、改配额、封禁与分组', async () => {
    vi.spyOn(api, 'adminUsers').mockResolvedValue([
      {
        id: 'u1',
        username: 'alice',
        role: 'user',
        status: 'active',
        daily_quota_tokens: 0,
        group_id: null,
      },
    ])
    vi.spyOn(api, 'adminGroups').mockResolvedValue([{ id: 'g1', name: '研发组' }])
    const update = vi.spyOn(api, 'adminUpdateUser').mockResolvedValue({})

    const wrapper = mount(AdminUsers)
    await flushPromises()
    expect(wrapper.text()).toContain('alice')

    vi.spyOn(window, 'prompt').mockReturnValue('1000')
    await wrapper.findAll('tbody button')[0].trigger('click')
    expect(update).toHaveBeenCalledWith('u1', { daily_quota_tokens: 1000 })

    await wrapper.findAll('tbody button')[1].trigger('click')
    expect(update).toHaveBeenCalledWith('u1', { status: 'banned' })

    await wrapper.find('tbody select').setValue('g1')
    expect(update).toHaveBeenCalledWith('u1', { group_id: 'g1' })
  })
})
