import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import KnowledgeAdminPage from '../pages/KnowledgeAdminPage.vue'
import { knowledgeAdminApi } from '../../admin-api.js'
import { getAuthUser } from '../../auth/session.js'

vi.mock('../../admin-api.js', () => ({
  knowledgeAdminApi: {
    listDocuments: vi.fn(),
    getDocument: vi.fn(),
    listDocumentVersions: vi.fn(),
    getDocumentVersion: vi.fn(),
    createDocument: vi.fn(),
    updateDocument: vi.fn(),
    replaceDocument: vi.fn(),
    deleteDocument: vi.fn(),
    restoreDocument: vi.fn(),
    rollbackDocument: vi.fn()
  }
}))

vi.mock('../../auth/session.js', () => ({
  getAuthUser: vi.fn()
}))

function makeDocument(overrides = {}) {
  return {
    document_id: 'doc_alpha',
    filename: 'alpha.txt',
    file_type: '.txt',
    size: 1024,
    chunk_count: 4,
    description: 'alpha doc',
    tags: ['faq'],
    published: true,
    visible_to_frontend: true,
    allowed_roles: ['user', 'admin'],
    deleted: false,
    updated_at: '2026-04-15T12:00:00',
    ...overrides
  }
}

function makeVersion(overrides = {}) {
  return {
    version_id: 'ver_current',
    version_no: 2,
    action: 'replace',
    source_version_id: null,
    filename: 'alpha-v2.txt',
    description: 'release doc',
    tags: ['release'],
    checksum: 'abc123',
    chunk_count: 2,
    size: 2048,
    created_at: '2026-04-15T12:05:00',
    created_by: 'admin-2',
    is_current: true,
    ...overrides
  }
}

function findButton(wrapper, label) {
  const button = wrapper
    .findAll('button')
    .find((item) => item.text().includes(label))
  if (!button) {
    throw new Error(`button not found: ${label}`)
  }
  return button
}

describe('KnowledgeAdminPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getAuthUser.mockReturnValue({ role: 'admin' })
    window.confirm = vi.fn(() => true)
    knowledgeAdminApi.listDocumentVersions.mockResolvedValue({
      data: {
        document_id: 'doc_alpha',
        current_version_id: null,
        versions: []
      }
    })
  })

  it('renders document metrics and keeps operator in read-only mode', async () => {
    getAuthUser.mockReturnValue({ role: 'operator' })
    knowledgeAdminApi.listDocuments.mockResolvedValue({
      data: {
        documents: [makeDocument()],
        total: 1
      }
    })

    const wrapper = mount(KnowledgeAdminPage)
    await flushPromises()

    expect(wrapper.text()).toContain('alpha.txt')
    expect(wrapper.text()).toContain('4 个分块')
    expect(wrapper.text()).toContain('运营只读')
    expect(wrapper.get('[data-testid="knowledge-upload-trigger"]').attributes('disabled')).toBeDefined()
  })

  it('renders independent list and detail scroll panes', async () => {
    knowledgeAdminApi.listDocuments.mockResolvedValue({
      data: {
        documents: [makeDocument()],
        total: 1
      }
    })

    const wrapper = mount(KnowledgeAdminPage)
    await flushPromises()

    expect(wrapper.get('[data-testid="knowledge-list-scroll"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="knowledge-detail-scroll"]').exists()).toBe(true)
  })

  it('accepts html and xlsx files in the admin upload inputs', async () => {
    knowledgeAdminApi.listDocuments.mockResolvedValue({
      data: {
        documents: [makeDocument()],
        total: 1
      }
    })

    const wrapper = mount(KnowledgeAdminPage)
    await flushPromises()

    const expectedAccept = '.txt,.pdf,.docx,.html,.htm,.xlsx'
    const fileInputs = wrapper.findAll('input[type="file"]')
    expect(fileInputs).toHaveLength(2)
    expect(fileInputs[0].attributes('accept')).toBe(expectedAccept)
    expect(fileInputs[1].attributes('accept')).toBe(expectedAccept)
  })

  it('keeps wheel scrolling isolated to the hovered pane', async () => {
    knowledgeAdminApi.listDocuments.mockResolvedValue({
      data: {
        documents: [makeDocument()],
        total: 1
      }
    })

    const wrapper = mount(KnowledgeAdminPage)
    await flushPromises()

    const listPane = wrapper.get('[data-testid="knowledge-list-scroll"]').element
    const detailPane = wrapper.get('[data-testid="knowledge-detail-scroll"]').element

    Object.defineProperty(listPane, 'clientHeight', { value: 120, configurable: true })
    Object.defineProperty(listPane, 'scrollHeight', { value: 360, configurable: true })
    listPane.scrollTop = 24
    detailPane.scrollTop = 0

    await wrapper.get('[data-testid="knowledge-list-scroll"]').trigger('wheel', { deltaY: 40 })

    expect(listPane.scrollTop).toBe(64)
    expect(detailPane.scrollTop).toBe(0)
  })

  it('lets admin filter deleted documents and exposes action buttons', async () => {
    knowledgeAdminApi.listDocuments.mockResolvedValue({
      data: {
        documents: [
          makeDocument({
            document_id: 'doc_deleted',
            filename: 'deleted.txt',
            size: 256,
            chunk_count: 1,
            description: 'deleted doc',
            tags: ['archive'],
            published: false,
            visible_to_frontend: false,
            allowed_roles: ['admin'],
            deleted: true,
            updated_at: '2026-04-15T12:30:00'
          })
        ],
        total: 1
      }
    })

    const wrapper = mount(KnowledgeAdminPage)
    await flushPromises()

    expect(wrapper.get('[data-testid="knowledge-status-filter"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="knowledge-upload-trigger"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.text()).toContain('已删除')
    expect(wrapper.text()).toContain('恢复文档')
  })

  it('saves metadata and refreshes the list with updated values', async () => {
    knowledgeAdminApi.listDocuments
      .mockResolvedValueOnce({
        data: {
          documents: [makeDocument()],
          total: 1
        }
      })
      .mockResolvedValueOnce({
        data: {
          documents: [
            makeDocument({
              description: 'updated doc',
              tags: ['release', 'faq'],
              published: false,
              visible_to_frontend: false
            })
          ],
          total: 1
        }
      })

    knowledgeAdminApi.updateDocument.mockResolvedValue({
      data: {
        document_id: 'doc_alpha',
        filename: 'alpha.txt'
      }
    })

    const wrapper = mount(KnowledgeAdminPage)
    await flushPromises()

    await wrapper.get('textarea').setValue('updated doc')
    await wrapper.findAll('.form-field input[type="text"]')[0].setValue('release, faq')
    await findButton(wrapper, '保存设置').trigger('click')
    await flushPromises()

    expect(knowledgeAdminApi.updateDocument).toHaveBeenCalledWith('doc_alpha', {
      description: 'updated doc',
      tags: ['release', 'faq'],
      visible_to_frontend: true,
      published: true,
      allowed_roles: ['user', 'admin']
    })
    expect(knowledgeAdminApi.listDocuments).toHaveBeenCalledTimes(2)
    expect(wrapper.get('textarea').element.value).toBe('updated doc')
    expect(wrapper.text()).toContain('release、faq')
    expect(wrapper.text()).toContain('已更新')
  })

  it('refreshes the active list after deleting a document', async () => {
    knowledgeAdminApi.listDocuments
      .mockResolvedValueOnce({
        data: {
          documents: [makeDocument()],
          total: 1
        }
      })
      .mockResolvedValueOnce({
        data: {
          documents: [],
          total: 0
        }
      })

    knowledgeAdminApi.deleteDocument.mockResolvedValue({
      data: {
        document_id: 'doc_alpha',
        filename: 'alpha.txt',
        deleted: true
      }
    })

    const wrapper = mount(KnowledgeAdminPage)
    await flushPromises()

    await findButton(wrapper, '删除文档').trigger('click')
    await flushPromises()

    expect(window.confirm).toHaveBeenCalled()
    expect(knowledgeAdminApi.deleteDocument).toHaveBeenCalledWith('doc_alpha')
    expect(knowledgeAdminApi.listDocuments).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('当前筛选条件下没有可显示的知识文件')
  })

  it('restores a deleted document, resets its state, and switches back to active status', async () => {
    knowledgeAdminApi.listDocuments
      .mockResolvedValueOnce({
        data: {
          documents: [],
          total: 0
        }
      })
      .mockResolvedValueOnce({
        data: {
          documents: [
            makeDocument({
              document_id: 'doc_deleted',
              filename: 'deleted.txt',
              published: false,
              visible_to_frontend: false,
              deleted: true
            })
          ],
          total: 1
        }
      })
      .mockResolvedValueOnce({
        data: {
          documents: [
            makeDocument({
              document_id: 'doc_deleted',
              filename: 'deleted.txt',
              published: false,
              visible_to_frontend: false,
              deleted: false
            })
          ],
          total: 1
        }
      })

    knowledgeAdminApi.restoreDocument.mockResolvedValue({
      data: {
        document_id: 'doc_deleted',
        filename: 'deleted.txt',
        deleted: false,
        published: false,
        visible_to_frontend: false
      }
    })

    const wrapper = mount(KnowledgeAdminPage)
    await flushPromises()

    await wrapper.get('[data-testid="knowledge-status-filter"]').setValue('deleted')
    await flushPromises()
    await findButton(wrapper, '恢复文档').trigger('click')
    await flushPromises()

    expect(knowledgeAdminApi.restoreDocument).toHaveBeenCalledWith('doc_deleted')
    expect(knowledgeAdminApi.listDocuments).toHaveBeenCalledTimes(3)
    expect(knowledgeAdminApi.listDocuments.mock.calls[2][0]).toEqual({
      keyword: undefined,
      status: 'active'
    })
    expect(wrapper.get('[data-testid="knowledge-status-filter"]').element.value).toBe('active')
    expect(wrapper.text()).toContain('草稿')
    expect(wrapper.text()).toContain('前台隐藏')
  })

  it('replaces a document and refreshes displayed metrics', async () => {
    knowledgeAdminApi.listDocuments
      .mockResolvedValueOnce({
        data: {
          documents: [makeDocument()],
          total: 1
        }
      })
      .mockResolvedValueOnce({
        data: {
          documents: [
            makeDocument({
              filename: 'alpha-v2.txt',
              chunk_count: 2,
              size: 2048
            })
          ],
          total: 1
        }
      })

    knowledgeAdminApi.replaceDocument.mockResolvedValue({
      data: {
        document_id: 'doc_alpha',
        filename: 'alpha-v2.txt',
        chunk_count: 2
      }
    })

    const wrapper = mount(KnowledgeAdminPage)
    await flushPromises()

    const file = new File(['line-1\nline-2'], 'alpha-v2.txt', { type: 'text/plain' })
    const replaceInput = wrapper.findAll('input[type="file"]')[1]
    Object.defineProperty(replaceInput.element, 'files', {
      value: [file],
      configurable: true
    })
    await replaceInput.trigger('change')
    await flushPromises()

    expect(knowledgeAdminApi.replaceDocument).toHaveBeenCalledWith('doc_alpha', file)
    expect(knowledgeAdminApi.listDocuments).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('alpha-v2.txt')
    expect(wrapper.text()).toContain('2 个分块')
  })
  it('loads version history and shows the selected version preview', async () => {
    knowledgeAdminApi.listDocuments.mockResolvedValue({
      data: {
        documents: [makeDocument()],
        total: 1
      }
    })
    knowledgeAdminApi.listDocumentVersions.mockResolvedValue({
      data: {
        document_id: 'doc_alpha',
        current_version_id: 'ver_current',
        versions: [
          makeVersion(),
          makeVersion({
            version_id: 'ver_v1',
            version_no: 1,
            action: 'create',
            filename: 'alpha.txt',
            description: 'alpha doc',
            tags: ['faq'],
            checksum: 'def456',
            chunk_count: 4,
            size: 1024,
            created_at: '2026-04-15T12:00:00',
            created_by: 'admin-1',
            is_current: false
          })
        ]
      }
    })

    const wrapper = mount(KnowledgeAdminPage)
    await flushPromises()

    expect(knowledgeAdminApi.listDocumentVersions).toHaveBeenCalledWith('doc_alpha')
    expect(wrapper.get('[data-testid="knowledge-version-panel"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="knowledge-version-row-ver_current"]').text()).toContain('alpha-v2.txt')
    expect(wrapper.get('[data-testid="knowledge-version-preview"]').text()).toContain('release doc')
  })

  it('renders localized version details with complete metadata', async () => {
    knowledgeAdminApi.listDocuments.mockResolvedValue({
      data: {
        documents: [makeDocument()],
        total: 1
      }
    })
    knowledgeAdminApi.listDocumentVersions.mockResolvedValue({
      data: {
        document_id: 'doc_alpha',
        current_version_id: 'ver_current',
        versions: [
          makeVersion({
            version_id: 'ver_rollback',
            version_no: 3,
            action: 'rollback',
            source_version_id: 'ver_v1',
            filename: 'alpha.txt',
            description: 'rollback doc',
            tags: ['faq'],
            checksum: 'xyz999',
            chunk_count: 4,
            size: 1024,
            created_at: '2026-04-15T12:10:00',
            created_by: 'admin-3',
            is_current: true
          })
        ]
      }
    })

    const wrapper = mount(KnowledgeAdminPage)
    await flushPromises()

    const previewText = wrapper.get('[data-testid="knowledge-version-preview"]').text()
    expect(previewText).toContain('版本快照')
    expect(previewText).toContain('回滚')
    expect(previewText).toContain('文件大小')
    expect(previewText).toContain('1.0 KB')
    expect(previewText).toContain('来源版本')
    expect(previewText).toContain('ver_v1')
    expect(previewText).toContain('创建人')
    expect(previewText).toContain('admin-3')
    expect(previewText).not.toContain('Checksum')
  })

  it('rolls back a version and refreshes current metrics', async () => {
    knowledgeAdminApi.listDocuments
      .mockResolvedValueOnce({
        data: {
          documents: [makeDocument({ filename: 'alpha-v2.txt', chunk_count: 2, size: 2048 })],
          total: 1
        }
      })
      .mockResolvedValueOnce({
        data: {
          documents: [makeDocument({ filename: 'alpha.txt', chunk_count: 4, size: 1024 })],
          total: 1
        }
      })
    knowledgeAdminApi.listDocumentVersions
      .mockResolvedValueOnce({
        data: {
          document_id: 'doc_alpha',
          current_version_id: 'ver_current',
          versions: [
            makeVersion(),
            makeVersion({
              version_id: 'ver_v1',
              version_no: 1,
              action: 'create',
              filename: 'alpha.txt',
              description: 'alpha doc',
              tags: ['faq'],
              checksum: 'def456',
              chunk_count: 4,
              size: 1024,
              created_at: '2026-04-15T12:00:00',
              created_by: 'admin-1',
              is_current: false
            })
          ]
        }
      })
      .mockResolvedValueOnce({
        data: {
          document_id: 'doc_alpha',
          current_version_id: 'ver_rollback',
          versions: [
            makeVersion({
              version_id: 'ver_rollback',
              version_no: 3,
              action: 'rollback',
              source_version_id: 'ver_v1',
              filename: 'alpha.txt',
              description: 'alpha doc',
              tags: ['faq'],
              checksum: 'xyz999',
              chunk_count: 4,
              size: 1024,
              created_at: '2026-04-15T12:10:00',
              created_by: 'admin-3',
              is_current: true
            }),
            makeVersion({ is_current: false })
          ]
        }
      })
    knowledgeAdminApi.rollbackDocument.mockResolvedValue({
      data: {
        document_id: 'doc_alpha',
        filename: 'alpha.txt',
        chunk_count: 4,
        current_version_id: 'ver_rollback',
        new_version_id: 'ver_rollback',
        target_version_id: 'ver_v1'
      }
    })

    const wrapper = mount(KnowledgeAdminPage)
    await flushPromises()

    await wrapper.get('[data-testid="knowledge-version-row-ver_v1"]').trigger('click')
    await wrapper.get('[data-testid="knowledge-version-rollback"]').trigger('click')
    await flushPromises()

    expect(knowledgeAdminApi.rollbackDocument).toHaveBeenCalledWith('doc_alpha', {
      target_version_id: 'ver_v1',
      reason: ''
    })
    expect(wrapper.text()).toContain('alpha.txt')
    expect(wrapper.get('[data-testid="knowledge-version-row-ver_rollback"]').exists()).toBe(true)
  })
})
