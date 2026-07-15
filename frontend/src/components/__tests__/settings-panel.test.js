import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import SettingsPanel from '../SettingsPanel.vue'
import { authApi, healthApi, knowledgeBaseApi } from '../../api/index.js'

vi.mock('../../api/index.js', () => ({
  authApi: { me: vi.fn() },
  healthApi: { check: vi.fn() },
  knowledgeBaseApi: { getParams: vi.fn() },
  clearAuthSession: vi.fn(),
  getAuthToken: vi.fn(),
  getAuthUser: vi.fn(() => ({ user_id: 'u1', username: 'demo', role: 'user', status: 'active' })),
  setAuthSession: vi.fn(),
  updateAuthUser: vi.fn((value) => value)
}))

describe('SettingsPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    authApi.me.mockResolvedValue({ data: { user_id: 'u1', username: 'demo', role: 'user', status: 'active' } })
    healthApi.check.mockResolvedValue({ data: { status: 'ok', version: 'test' } })
    knowledgeBaseApi.getParams.mockResolvedValue({
      data: {
        params: { chunk_size: 400, top_k: 5 },
        cache_stats: {},
        metrics: {},
        frontend_policy: {
          knowledge_base: {
            intro_text: 'Visible docs only',
            empty_state_text: 'No documents',
            readonly_notice: 'Read only',
            show_document_metrics: true
          },
          settings: {
            show_summary: true,
            show_runtime_overview: false,
            show_permission_notice: false,
            readonly_notice: '设置页只读展示'
          }
        }
      }
    })
  })

  it('uses frontend policy to hide runtime overview and show readonly notice', async () => {
    const wrapper = mount(SettingsPanel)
    await flushPromises()

    expect(wrapper.text()).toContain('设置页只读展示')
    expect(wrapper.text()).not.toContain('分块大小')
  })
})
