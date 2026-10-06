import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import AdminPublicKeys from './AdminPublicKeys.vue'
import { api } from '../../api/client'
import type { ApiKey } from '../../api/types'

describe('AdminPublicKeys', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('无公有 Key 时展示空态，并可新增', async () => {
    vi.spyOn(api, 'listPublicKeys').mockResolvedValue([])
    const create = vi
      .spyOn(api, 'createPublicKey')
      .mockResolvedValue({} as unknown as ApiKey)

    const wrapper = mount(AdminPublicKeys)
    await flushPromises()
    expect(wrapper.text()).toContain('暂无公有 Key')

    const inputs = wrapper.findAll('form input')
    await inputs[0].setValue('公共池')
    await inputs[1].setValue('sk-xxxx')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(create).toHaveBeenCalled()
  })

  it('列出公有 Key 并可测试/停用/删除', async () => {
    const key = {
      id: 'k1',
      provider_name: '通道',
      base_url: 'https://api.openai.com/v1',
      models: ['gpt-4o'],
      masked_key: 'sk-...abcd',
      rate_limits: { rpm: 60, rpd: 1000, tpm: 0, tpd: 0 },
      weight: 1,
      status: 'active',
      pool: 'public',
      created_at: '2026-01-01T00:00:00Z',
    } as ApiKey
    vi.spyOn(api, 'listPublicKeys').mockResolvedValue([key])
    vi.spyOn(api, 'testKey').mockResolvedValue({
      ok: true,
      status_code: 200,
      latency_ms: 5,
      error: null,
    })
    vi.spyOn(api, 'updateKey').mockResolvedValue(key)
    vi.spyOn(api, 'deleteKey').mockResolvedValue(null)
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    const wrapper = mount(AdminPublicKeys)
    await flushPromises()
    expect(wrapper.text()).toContain('通道')

    const buttons = wrapper.findAll('tbody button')
    await buttons[0].trigger('click')
    await flushPromises()
    expect(api.testKey).toHaveBeenCalledWith('k1')

    await wrapper.findAll('tbody button')[1].trigger('click')
    expect(api.updateKey).toHaveBeenCalled()

    await wrapper.findAll('tbody button')[2].trigger('click')
    await flushPromises()
    expect(api.deleteKey).toHaveBeenCalledWith('k1')
  })
})
