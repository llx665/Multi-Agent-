import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AdminApp from '../../AdminApp.vue'
import { authApi } from '../../api/index.js'
import { clearAuthSession, getAuthUser, updateAuthUser } from '../../auth/session.js'

vi.mock('../../api/index.js', () => ({
  authApi: {
    me: vi.fn()
  }
}))

vi.mock('../../auth/session.js', () => ({
  getAuthUser: vi.fn(),
  clearAuthSession: vi.fn(),
  updateAuthUser: vi.fn((user) => user)
}))

describe('AdminApp shell', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders auth panel when no session exists', async () => {
    getAuthUser.mockReturnValue(null)

    const wrapper = mount(AdminApp, {
      global: {
        stubs: {
          AuthPanel: { template: '<div data-testid="auth-panel">auth</div>' },
          RouterView: { template: '<div data-testid="router-view">router</div>' }
        }
      }
    })

    await flushPromises()

    expect(wrapper.find('[data-testid="auth-panel"]').exists()).toBe(true)
    expect(authApi.me).not.toHaveBeenCalled()
  })

  it('shows denied state for plain user', async () => {
    getAuthUser.mockReturnValue({ user_id: 'u1', username: 'plain.user' })
    authApi.me.mockResolvedValue({
      data: { user_id: 'u1', username: 'plain.user', role: 'user', status: 'active' }
    })

    const wrapper = mount(AdminApp, {
      global: {
        stubs: {
          AuthPanel: { template: '<div data-testid="auth-panel">auth</div>' },
          RouterView: { template: '<div data-testid="router-view">router</div>' }
        }
      }
    })

    await flushPromises()

    expect(wrapper.text()).toContain('无后台访问权限')
    expect(updateAuthUser).toHaveBeenCalledWith({
      user_id: 'u1',
      username: 'plain.user',
      role: 'user',
      status: 'active'
    })
    expect(clearAuthSession).toHaveBeenCalledTimes(0)
  })
})
