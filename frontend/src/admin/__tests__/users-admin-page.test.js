import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import UsersAdminPage from '../pages/UsersAdminPage.vue'
import { userAdminApi } from '../../admin-api.js'
import { getAuthUser } from '../../auth/session.js'

vi.mock('../../admin-api.js', () => ({
  userAdminApi: {
    listUsers: vi.fn(),
    getUser: vi.fn(),
    updateStatus: vi.fn(),
    updateRole: vi.fn()
  }
}))

vi.mock('../../auth/session.js', () => ({
  getAuthUser: vi.fn()
}))

function makeListUser(overrides = {}) {
  return {
    user_id: 'u_001',
    username: 'alpha.user',
    role: 'user',
    status: 'active',
    updated_at: '2026-04-15T10:00:00',
    ...overrides
  }
}

function makeDetailUser(overrides = {}) {
  return {
    user_id: 'u_001',
    username: 'alpha.user',
    role: 'user',
    status: 'active',
    created_at: '2026-04-10T10:00:00',
    updated_at: '2026-04-15T10:00:00',
    last_login_at: '2026-04-15T09:00:00',
    password_updated_at: '2026-04-13T10:00:00',
    ...overrides
  }
}

function deferred() {
  let resolve
  let reject
  const promise = new Promise((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

describe('UsersAdminPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getAuthUser.mockReturnValue({ user_id: 'admin_1', role: 'admin', username: 'admin.one' })
  })

  it('loads first user detail after list fetch and renders detail panel', async () => {
    userAdminApi.listUsers.mockResolvedValue({
      data: {
        users: [
          makeListUser({ user_id: 'u_001', username: 'alpha.user' }),
          makeListUser({ user_id: 'u_002', username: 'beta.user' })
        ]
      }
    })
    userAdminApi.getUser.mockResolvedValue({
      data: makeDetailUser({ user_id: 'u_001', username: 'alpha.user' })
    })

    const wrapper = mount(UsersAdminPage)
    await flushPromises()

    expect(userAdminApi.listUsers).toHaveBeenCalledTimes(1)
    expect(userAdminApi.getUser).toHaveBeenCalledWith('u_001')
    expect(wrapper.get('[data-testid="user-detail-panel"]').text()).toContain('alpha.user')
    expect(wrapper.get('[data-testid="detail-user-id"]').text()).toContain('u_001')
  })

  it('shows status controls only for admin and disables status action on admin target with hint', async () => {
    getAuthUser.mockReturnValue({ user_id: 'admin_self', role: 'admin', username: 'admin.self' })
    userAdminApi.listUsers.mockResolvedValue({
      data: {
        users: [makeListUser({ user_id: 'admin_2', username: 'admin.target', role: 'admin', status: 'active' })]
      }
    })
    userAdminApi.getUser.mockResolvedValue({
      data: makeDetailUser({ user_id: 'admin_2', username: 'admin.target', role: 'admin', status: 'active' })
    })

    const wrapper = mount(UsersAdminPage)
    await flushPromises()

    expect(wrapper.find('[data-testid="role-editor"]').exists()).toBe(false)
    const statusBtn = wrapper.get('[data-testid="status-toggle-btn"]')
    expect(statusBtn.attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-testid="status-disabled-hint"]').text()).toContain('管理员不能操作管理员或超管账号')
  })

  it('disables status action when admin selects own account and shows hint', async () => {
    getAuthUser.mockReturnValue({ user_id: 'admin_self', role: 'admin', username: 'admin.self' })
    userAdminApi.listUsers.mockResolvedValue({
      data: {
        users: [makeListUser({ user_id: 'admin_self', username: 'admin.self', role: 'admin', status: 'active' })]
      }
    })
    userAdminApi.getUser.mockResolvedValue({
      data: makeDetailUser({ user_id: 'admin_self', username: 'admin.self', role: 'admin', status: 'active' })
    })

    const wrapper = mount(UsersAdminPage)
    await flushPromises()

    const statusBtn = wrapper.get('[data-testid="status-toggle-btn"]')
    expect(statusBtn.attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-testid="status-disabled-hint"]').text()).toContain('管理员不能操作自己的账号状态')
  })

  it('prevents operating stale detail while switching selected user', async () => {
    getAuthUser.mockReturnValue({ user_id: 'root_1', role: 'super_admin', username: 'root' })
    const secondDetail = deferred()

    userAdminApi.listUsers.mockResolvedValue({
      data: {
        users: [
          makeListUser({ user_id: 'u_001', username: 'alpha.user', role: 'user' }),
          makeListUser({ user_id: 'u_002', username: 'beta.user', role: 'operator' })
        ]
      }
    })
    userAdminApi.getUser
      .mockResolvedValueOnce({ data: makeDetailUser({ user_id: 'u_001', role: 'user' }) })
      .mockImplementationOnce(() => secondDetail.promise)

    const wrapper = mount(UsersAdminPage)
    await flushPromises()

    expect(wrapper.get('[data-testid="detail-user-id"]').text()).toContain('u_001')

    await wrapper.get('[data-testid="user-list-item-u_002"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('详情加载中…')
    expect(wrapper.find('[data-testid="detail-user-id"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="status-toggle-btn"]').exists()).toBe(false)

    secondDetail.resolve({ data: makeDetailUser({ user_id: 'u_002', username: 'beta.user', role: 'operator' }) })
    await flushPromises()

    expect(wrapper.get('[data-testid="detail-user-id"]').text()).toContain('u_002')
    expect(wrapper.find('[data-testid="status-toggle-btn"]').exists()).toBe(true)
  })

  it('ignores out-of-order detail responses and keeps current selection detail', async () => {
    getAuthUser.mockReturnValue({ user_id: 'root_1', role: 'super_admin', username: 'root' })
    const u2Slow = deferred()
    const u1Fast = deferred()

    userAdminApi.listUsers.mockResolvedValue({
      data: {
        users: [
          makeListUser({ user_id: 'u_001', username: 'alpha.user', role: 'user' }),
          makeListUser({ user_id: 'u_002', username: 'beta.user', role: 'operator' })
        ]
      }
    })

    userAdminApi.getUser
      .mockResolvedValueOnce({ data: makeDetailUser({ user_id: 'u_001', role: 'user' }) })
      .mockImplementationOnce(() => u2Slow.promise)
      .mockImplementationOnce(() => u1Fast.promise)

    const wrapper = mount(UsersAdminPage)
    await flushPromises()

    await wrapper.get('[data-testid="user-list-item-u_002"]').trigger('click')
    await wrapper.get('[data-testid="user-list-item-u_001"]').trigger('click')

    u1Fast.resolve({ data: makeDetailUser({ user_id: 'u_001', username: 'alpha.user', role: 'admin' }) })
    await flushPromises()
    expect(wrapper.get('[data-testid="detail-user-id"]').text()).toContain('u_001')
    expect(wrapper.get('[data-testid="detail-role"]').text()).toContain('管理员')

    u2Slow.resolve({ data: makeDetailUser({ user_id: 'u_002', username: 'beta.user', role: 'operator' }) })
    await flushPromises()

    expect(wrapper.get('[data-testid="detail-user-id"]').text()).toContain('u_001')
    expect(wrapper.get('[data-testid="detail-role"]').text()).toContain('管理员')
  })

  it('shows detail load error and allows retry on same selected user', async () => {
    userAdminApi.listUsers.mockResolvedValue({
      data: {
        users: [makeListUser({ user_id: 'u_001', username: 'alpha.user' })]
      }
    })
    userAdminApi.getUser
      .mockRejectedValueOnce(new Error('load detail failed'))
      .mockResolvedValueOnce({
        data: makeDetailUser({ user_id: 'u_001', username: 'alpha.user' })
      })

    const wrapper = mount(UsersAdminPage)
    await flushPromises()

    expect(wrapper.get('[data-testid="detail-load-error"]').text()).toContain('加载账号详情失败')
    expect(wrapper.find('[data-testid="detail-user-id"]').exists()).toBe(false)

    await wrapper.get('[data-testid="user-list-item-u_001"]').trigger('click')
    await flushPromises()

    expect(userAdminApi.getUser).toHaveBeenCalledTimes(2)
    expect(wrapper.get('[data-testid="detail-user-id"]').text()).toContain('u_001')
  })

  it('refreshes list and detail after status update', async () => {
    getAuthUser.mockReturnValue({ user_id: 'root_1', role: 'super_admin', username: 'root' })

    userAdminApi.listUsers
      .mockResolvedValueOnce({
        data: {
          users: [makeListUser({ user_id: 'u_001', status: 'active' })]
        }
      })
      .mockResolvedValueOnce({
        data: {
          users: [makeListUser({ user_id: 'u_001', status: 'disabled' })]
        }
      })

    userAdminApi.getUser
      .mockResolvedValueOnce({
        data: makeDetailUser({ user_id: 'u_001', status: 'active' })
      })
      .mockResolvedValueOnce({
        data: makeDetailUser({ user_id: 'u_001', status: 'disabled' })
      })

    userAdminApi.updateStatus.mockResolvedValue({
      data: {
        user_id: 'u_001',
        status: 'disabled'
      }
    })

    const wrapper = mount(UsersAdminPage)
    await flushPromises()
    expect(wrapper.get('[data-testid="user-list-status-u_001"]').text()).toContain('启用')

    await wrapper.get('[data-testid="status-toggle-btn"]').trigger('click')
    await flushPromises()

    expect(userAdminApi.updateStatus).toHaveBeenCalledWith('u_001', 'disabled')
    expect(userAdminApi.listUsers).toHaveBeenCalledTimes(2)
    expect(userAdminApi.getUser).toHaveBeenCalledTimes(2)
    expect(wrapper.get('[data-testid="user-list-status-u_001"]').text()).toContain('停用')
    expect(wrapper.get('[data-testid="detail-status"]').text()).toContain('停用')
  })

  it('allows super admin to edit another user role', async () => {
    getAuthUser.mockReturnValue({ user_id: 'root_1', role: 'super_admin', username: 'root' })

    userAdminApi.listUsers
      .mockResolvedValueOnce({
        data: {
          users: [makeListUser({ user_id: 'u_001', role: 'user' })]
        }
      })
      .mockResolvedValueOnce({
        data: {
          users: [makeListUser({ user_id: 'u_001', role: 'admin' })]
        }
      })

    userAdminApi.getUser
      .mockResolvedValueOnce({
        data: makeDetailUser({ user_id: 'u_001', role: 'user' })
      })
      .mockResolvedValueOnce({
        data: makeDetailUser({ user_id: 'u_001', role: 'admin' })
      })

    userAdminApi.updateRole.mockResolvedValue({
      data: {
        user_id: 'u_001',
        role: 'admin'
      }
    })

    const wrapper = mount(UsersAdminPage)
    await flushPromises()

    expect(wrapper.find('[data-testid="role-editor"]').exists()).toBe(true)
    await wrapper.get('[data-testid="role-editor"]').setValue('admin')
    await wrapper.get('[data-testid="role-save-btn"]').trigger('click')
    await flushPromises()

    expect(userAdminApi.updateRole).toHaveBeenCalledWith('u_001', 'admin')
    expect(wrapper.get('[data-testid="detail-role"]').text()).toContain('管理员')
  })
})
