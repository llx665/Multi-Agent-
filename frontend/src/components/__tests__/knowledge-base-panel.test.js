import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import KnowledgeBasePanel from '../KnowledgeBasePanel.vue'
import { knowledgeBaseApi } from '../../api/index.js'

vi.mock('../../api/index.js', () => ({
  knowledgeBaseApi: {
    getDocuments: vi.fn(),
    getDocument: vi.fn(),
    getParams: vi.fn()
  }
}))

describe('KnowledgeBasePanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('uses frontend policy copy and hides document metrics when disabled', async () => {
    knowledgeBaseApi.getDocuments.mockResolvedValue({
      data: {
        documents: [
          {
            id: 'doc_alpha',
            filename: 'alpha.txt',
            file_path: 'D:/docs/alpha.txt',
            file_type: '.txt',
            chunk_count: 4,
            size: 1024,
            upload_time: '2026-04-15T12:00:00',
            update_time: '2026-04-15T12:30:00'
          }
        ],
        total: 1
      }
    })
    knowledgeBaseApi.getParams.mockResolvedValue({
      data: {
        params: {},
        cache_stats: {},
        metrics: {},
        frontend_policy: {
          knowledge_base: {
            intro_text: 'Visible docs only',
            empty_state_text: 'No documents',
            readonly_notice: 'Read only',
            show_document_metrics: false
          },
          settings: {
            show_summary: true,
            show_runtime_overview: true,
            show_permission_notice: true,
            readonly_notice: 'Contact admin'
          }
        }
      }
    })
    knowledgeBaseApi.getDocument.mockResolvedValue({
      data: {
        id: 'doc_alpha',
        filename: 'alpha.txt',
        content: 'alpha body',
        chunks: []
      }
    })

    const wrapper = mount(KnowledgeBasePanel)
    await flushPromises()

    expect(knowledgeBaseApi.getParams).toHaveBeenCalledTimes(1)
    expect(knowledgeBaseApi.getDocument).toHaveBeenCalledWith('doc_alpha')
    expect(wrapper.text()).toContain('Visible docs only')
    expect(wrapper.text()).toContain('Read only')
    expect(wrapper.text()).not.toContain('文件类型')
    expect(wrapper.text()).not.toContain('文档 ID')
    expect(wrapper.text()).toContain('alpha body')
  })
})
