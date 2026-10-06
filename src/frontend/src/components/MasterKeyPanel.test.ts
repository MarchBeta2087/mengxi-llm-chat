import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import MasterKeyPanel from './MasterKeyPanel.vue'
import { api } from '../api/client'

describe('MasterKeyPanel', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
  })

  it('未初始化时可初始化并展示恢复码', async () => {
    vi.spyOn(api, 'adminKek').mockResolvedValue({ profile: 'A', state: 'uninitialized' })
    vi.spyOn(api, 'adminRecoveryStatus').mockResolvedValue({ remaining: 0 })
    const init = vi
      .spyOn(api, 'adminKekInitialize')
      .mockResolvedValue({ profile: 'A', state: 'unlocked', recovery_codes: ['AAAA-BBBB-CCCC'] })

    const wrapper = mount(MasterKeyPanel)
    await flushPromises()
    expect(wrapper.text()).toContain('uninitialized')

    await wrapper.find('input[type=password]').setValue('passphrase123')
    await wrapper.find('.ops button').trigger('click')
    await flushPromises()

    expect(init).toHaveBeenCalledWith('passphrase123')
    expect(wrapper.text()).toContain('AAAA-BBBB-CCCC')
  })

  it('已解锁时可锁定并重新生成恢复码', async () => {
    vi.spyOn(api, 'adminKek').mockResolvedValue({ profile: 'B', state: 'unlocked' })
    vi.spyOn(api, 'adminRecoveryStatus').mockResolvedValue({ remaining: 8 })
    const lock = vi.spyOn(api, 'adminKekLock').mockResolvedValue({ profile: 'B', state: 'locked' })
    const regen = vi
      .spyOn(api, 'adminRecoveryRegenerate')
      .mockResolvedValue({ codes: ['XXXX-XXXX-XXXX'] })

    const wrapper = mount(MasterKeyPanel)
    await flushPromises()

    const lockButton = wrapper.findAll('button').find((b) => b.text().includes('锁定'))!
    await lockButton.trigger('click')
    await flushPromises()
    expect(lock).toHaveBeenCalled()

    const regenButton = wrapper.findAll('button').find((b) => b.text().includes('重新生成'))!
    await regenButton.trigger('click')
    await flushPromises()
    expect(regen).toHaveBeenCalled()
    expect(wrapper.text()).toContain('XXXX-XXXX-XXXX')
  })

  it('已锁定时可解锁', async () => {
    vi.spyOn(api, 'adminKek').mockResolvedValue({ profile: 'A', state: 'locked' })
    vi.spyOn(api, 'adminRecoveryStatus').mockResolvedValue({ remaining: 5 })
    const unlock = vi
      .spyOn(api, 'adminKekUnlock')
      .mockResolvedValue({ profile: 'A', state: 'unlocked' })

    const wrapper = mount(MasterKeyPanel)
    await flushPromises()

    await wrapper.find('input[type=password]').setValue('passphrase123')
    const unlockButton = wrapper.findAll('button').find((b) => b.text().includes('解锁'))!
    await unlockButton.trigger('click')
    await flushPromises()
    expect(unlock).toHaveBeenCalledWith('passphrase123')
  })
})
