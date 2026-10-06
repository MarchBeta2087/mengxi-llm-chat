import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import AdminAudit from './AdminAudit.vue'
import { api } from '../../api/client'

describe('AdminAudit', () => {
  beforeEach(() => setActivePinia(createPinia()))
  afterEach(() => vi.unstubAllGlobals())

  it('加载审计、按回退过滤并导出 CSV', async () => {
    const audit = vi.spyOn(api, 'adminAudit').mockResolvedValue([])
    const exportCsv = vi.spyOn(api, 'exportAuditCsv').mockResolvedValue('id,status\n1,200\n')
    vi.stubGlobal('URL', {
      createObjectURL: vi.fn(() => 'blob:x'),
      revokeObjectURL: vi.fn(),
    })

    const wrapper = mount(AdminAudit)
    await flushPromises()
    expect(audit).toHaveBeenCalled()

    await wrapper.find('input[type=checkbox]').setValue(true)
    await flushPromises()
    expect(audit).toHaveBeenLastCalledWith('?fallback_only=true')

    await wrapper.findAll('button').find((b) => b.text().includes('导出'))!.trigger('click')
    await flushPromises()
    expect(exportCsv).toHaveBeenCalledWith('?fallback_only=true')
  })

  it('按状态过滤', async () => {
    const audit = vi.spyOn(api, 'adminAudit').mockResolvedValue([
      {
        created_at: '2026-01-01',
        user_id: 'u1',
        key_type: 'private',
        model: 'gpt-4o',
        status: 200,
        tokens_in: 1,
        tokens_out: 2,
        fallback_to_public: false,
      },
    ])
    const wrapper = mount(AdminAudit)
    await flushPromises()
    expect(wrapper.text()).toContain('private')

    await wrapper.find('select').setValue('200')
    await flushPromises()
    expect(audit).toHaveBeenLastCalledWith('?status=200')
  })
})
