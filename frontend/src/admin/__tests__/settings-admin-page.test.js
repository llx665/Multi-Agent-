import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import SettingsAdminPage from '../pages/SettingsAdminPage.vue'
import { settingsAdminApi } from '../../admin-api.js'

vi.mock('../../admin-api.js', () => ({
  settingsAdminApi: {
    getSummary: vi.fn(),
    updateRuntime: vi.fn(),
    updateFrontendPolicy: vi.fn()
  }
}))

function makeSummary() {
  return {
    runtime_params: {
      chunk_size: 400,
      chunk_overlap: 50,
      top_k: 5,
      similarity_threshold: 0.3,
      enable_cache: true,
      enable_rerank: true,
      enable_hybrid: true,
      enable_self_rag: false
    },
    permission_model: {
      roles: {
        admin: {
          label: '管理员',
          capabilities: ['系统设置']
        }
      }
    },
    frontend_policy: {
      knowledge_base: {
        intro_text: 'Visible docs only',
        empty_state_text: 'No documents',
        readonly_notice: 'Read only',
        show_document_metrics: true
      },
      settings: {
        show_summary: true,
        show_runtime_overview: true,
        show_permission_notice: true,
        readonly_notice: 'Contact admin'
      }
    }
  }
}

describe('SettingsAdminPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    settingsAdminApi.getSummary.mockResolvedValue({ data: makeSummary() })
    settingsAdminApi.updateRuntime.mockResolvedValue({
      data: {
        params: {
          chunk_size: 520,
          chunk_overlap: 60,
          top_k: 8,
          similarity_threshold: 0.35,
          enable_cache: false,
          enable_rerank: true,
          enable_hybrid: true,
          enable_self_rag: false
        }
      }
    })
    settingsAdminApi.updateFrontendPolicy.mockResolvedValue({
      data: {
        policy: {
          knowledge_base: {
            intro_text: 'Updated intro',
            empty_state_text: 'Still empty',
            readonly_notice: 'Read only',
            show_document_metrics: false
          },
          settings: {
            show_summary: true,
            show_runtime_overview: false,
            show_permission_notice: true,
            readonly_notice: 'Handled by admins'
          }
        }
      }
    })
  })

  it('loads runtime params and frontend policy into separate forms', async () => {
    const wrapper = mount(SettingsAdminPage)
    await flushPromises()

    expect(settingsAdminApi.getSummary).toHaveBeenCalledTimes(1)
    expect(wrapper.get('[data-testid="runtime-chunk-size"]').element.value).toBe('400')
    expect(wrapper.get('[data-testid="runtime-top-k"]').element.value).toBe('5')
    expect(wrapper.get('[data-testid="policy-intro-text"]').element.value).toBe('Visible docs only')
    expect(wrapper.get('[data-testid="policy-show-runtime-overview"]').element.checked).toBe(true)
  })

  it('saves runtime params without calling frontend policy update', async () => {
    const wrapper = mount(SettingsAdminPage)
    await flushPromises()

    await wrapper.get('[data-testid="runtime-chunk-size"]').setValue('520')
    await wrapper.get('[data-testid="runtime-chunk-overlap"]').setValue('60')
    await wrapper.get('[data-testid="runtime-top-k"]').setValue('8')
    await wrapper.get('[data-testid="save-runtime-btn"]').trigger('click')
    await flushPromises()

    expect(settingsAdminApi.updateRuntime).toHaveBeenCalledWith({
      chunk_size: 520,
      chunk_overlap: 60,
      top_k: 8,
      similarity_threshold: 0.3,
      enable_cache: true,
      enable_rerank: true,
      enable_hybrid: true,
      enable_self_rag: false
    })
    expect(settingsAdminApi.updateFrontendPolicy).not.toHaveBeenCalled()
    expect(wrapper.get('[data-testid="runtime-success"]').text()).toContain('已保存')
    expect(wrapper.find('[data-testid="frontend-policy-error"]').exists()).toBe(false)
  })

  it('shows frontend policy save errors without polluting runtime feedback', async () => {
    settingsAdminApi.updateFrontendPolicy.mockRejectedValue({
      response: { data: { detail: 'unsupported frontend policy fields' } }
    })

    const wrapper = mount(SettingsAdminPage)
    await flushPromises()

    await wrapper.get('[data-testid="policy-intro-text"]').setValue('New intro')
    await wrapper.get('[data-testid="policy-show-runtime-overview"]').setValue(false)
    await wrapper.get('[data-testid="save-frontend-policy-btn"]').trigger('click')
    await flushPromises()

    expect(settingsAdminApi.updateFrontendPolicy).toHaveBeenCalledTimes(1)
    expect(settingsAdminApi.updateRuntime).not.toHaveBeenCalled()
    expect(wrapper.get('[data-testid="frontend-policy-error"]').text()).toContain('unsupported frontend policy fields')
    expect(wrapper.find('[data-testid="runtime-error"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="runtime-success"]').exists()).toBe(false)
  })
})
