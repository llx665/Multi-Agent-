<template>
  <section class="knowledge-admin-page">
    <header class="page-hero">
      <div class="hero-copy">
        <p class="eyebrow">知识库管理</p>
        <h3>统一管理知识文件的上传、替换、软删除、恢复与前台显示策略</h3>
        <p>
          后台统一维护知识文件的元数据、前台可见性、发布状态、角色范围和分块指标。前台只读展示允许访问的文档，所有写操作都在这里完成。
        </p>
      </div>

      <div class="hero-actions">
        <span class="mode-pill" :class="{ readonly: isOperator }">
          {{ isOperator ? '运营只读' : '管理员可编辑' }}
        </span>
        <button
          data-testid="knowledge-upload-trigger"
          class="solid-btn"
          :disabled="isOperator || uploading"
          @click="openCreatePanel"
        >
          {{ uploading ? '上传中...' : '上传知识文件' }}
        </button>
      </div>
    </header>

    <div class="toolbar-card">
      <label class="search-field">
        <span>搜索</span>
        <input
          v-model.trim="filters.keyword"
          class="search-input"
          placeholder="搜索文件名、标签或描述"
          @keydown.enter.prevent="loadDocuments"
        />
      </label>

      <label class="filter-field">
        <span>状态</span>
        <select
          v-model="filters.status"
          data-testid="knowledge-status-filter"
          class="filter-select"
          @change="loadDocuments"
        >
          <option value="active">有效文档</option>
          <option value="deleted">已删除</option>
          <option value="all">全部文档</option>
        </select>
      </label>

      <button class="ghost-btn" :disabled="loading" @click="loadDocuments">
        {{ loading ? '刷新中...' : '刷新列表' }}
      </button>
    </div>

    <p v-if="successMessage" class="notice success">{{ successMessage }}</p>
    <p v-if="errorMessage" class="notice error">{{ errorMessage }}</p>
    <p v-if="isOperator" class="notice warning">
      当前账号为运营角色，仅可查看文件状态与指标，不能执行上传、发布、显隐、删除或恢复操作。
    </p>

    <div
      ref="workspaceGrid"
      data-testid="knowledge-workspace-grid"
      class="workspace-grid"
      :style="workspaceStyle"
    >
      <section class="table-card">
        <div class="table-head">
          <div>
            <p class="panel-label">文档列表</p>
            <strong>{{ documents.length }} 份文档</strong>
          </div>
          <span class="summary-pill">{{ filters.status === 'deleted' ? '回收视图' : '运营视图' }}</span>
        </div>

        <div v-if="loading && documents.length === 0" class="empty-panel">正在加载知识文件...</div>
        <div v-else-if="documents.length === 0" class="empty-panel">当前筛选条件下没有可显示的知识文件。</div>

        <div
          v-else
          data-testid="knowledge-list-scroll"
          class="table-shell"
          @wheel="handlePaneWheel"
        >
          <table class="knowledge-table">
            <thead>
              <tr>
                <th>文件</th>
                <th>标签</th>
                <th>大小</th>
                <th>分块数量</th>
                <th>状态</th>
                <th>更新时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="doc in documents"
                :key="doc.document_id"
                :class="{ active: selectedDocument?.document_id === doc.document_id }"
                @click="selectDocument(doc)"
              >
                <td>
                  <div class="primary-cell">
                    <strong>{{ doc.filename }}</strong>
                    <span>{{ doc.file_type }}</span>
                  </div>
                </td>
                <td>{{ formatTags(doc.tags) }}</td>
                <td>{{ formatFileSize(doc.size) }}</td>
                <td>{{ doc.chunk_count || 0 }} 个分块</td>
                <td>
                  <div class="status-stack">
                    <span class="status-pill" :class="statusClass(doc)">
                      {{ statusText(doc) }}
                    </span>
                    <span class="status-pill soft" :class="{ hidden: !doc.visible_to_frontend }">
                      {{ doc.visible_to_frontend ? '前台显示' : '前台隐藏' }}
                    </span>
                  </div>
                </td>
                <td>{{ formatDate(doc.updated_at || doc.update_time) }}</td>
                <td class="action-text">
                  {{ isOperator ? '运营只读' : doc.deleted ? '恢复文档' : '编辑文档' }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <aside class="detail-card">
        <div
          data-testid="knowledge-detail-scroll"
          class="detail-scroll"
          @wheel="handlePaneWheel"
        >
          <div v-if="!selectedDocument" class="empty-panel">
          选择左侧文档后，可以查看指标、编辑元数据，或执行替换、删除、恢复操作。
        </div>

          <template v-else>
          <div class="detail-head">
            <div>
              <p class="panel-label">文档详情</p>
              <h4>{{ selectedDocument.filename }}</h4>
              <p class="detail-id">{{ selectedDocument.document_id }}</p>
            </div>

            <div class="detail-status">
              <span class="status-pill" :class="statusClass(selectedDocument)">
                {{ statusText(selectedDocument) }}
              </span>
              <span class="status-pill soft" :class="{ hidden: !selectedDocument.visible_to_frontend }">
                {{ selectedDocument.visible_to_frontend ? '前台显示' : '前台隐藏' }}
              </span>
            </div>
          </div>

          <div class="metric-grid">
            <article class="metric-card">
              <span>文件大小</span>
              <strong>{{ formatFileSize(selectedDocument.size) }}</strong>
            </article>
            <article class="metric-card">
              <span>分块数量</span>
              <strong>{{ selectedDocument.chunk_count || 0 }} 个分块</strong>
            </article>
            <article class="metric-card">
              <span>最后更新</span>
              <strong>{{ formatDate(selectedDocument.updated_at || selectedDocument.update_time) }}</strong>
            </article>
          </div>

          <label class="form-field">
            <span>描述</span>
            <textarea
              v-model="selectedDocument.description"
              rows="4"
              :disabled="isOperator || selectedDocument.deleted || saving"
            />
          </label>

          <label class="form-field">
            <span>标签</span>
            <input
              v-model="selectedDocument.tag_input"
              type="text"
              placeholder="用逗号分隔多个标签"
              :disabled="isOperator || selectedDocument.deleted || saving"
            />
          </label>

          <div class="toggle-grid">
            <label class="toggle-card">
              <span>发布状态</span>
              <input
                v-model="selectedDocument.published"
                type="checkbox"
                :disabled="isOperator || selectedDocument.deleted || saving"
              />
            </label>

            <label class="toggle-card">
              <span>前台可见</span>
              <input
                v-model="selectedDocument.visible_to_frontend"
                type="checkbox"
                :disabled="isOperator || selectedDocument.deleted || saving"
              />
            </label>
          </div>

          <div class="role-block">
            <p class="panel-label">允许访问角色</p>
            <div class="role-grid">
              <label v-for="role in roleOptions" :key="role.value" class="role-chip">
                <input
                  type="checkbox"
                  :checked="selectedDocument.allowed_roles.includes(role.value)"
                  :disabled="isOperator || selectedDocument.deleted || saving"
                  @change="toggleRole(role.value, $event.target.checked)"
                />
                <span>{{ role.label }}</span>
              </label>
            </div>
          </div>

          <div class="detail-actions">
            <button
              class="solid-btn"
              :disabled="isOperator || selectedDocument.deleted || saving"
              @click="saveCurrent"
            >
              {{ saving ? '保存中...' : '保存设置' }}
            </button>

            <button
              class="ghost-btn"
              :disabled="isOperator || selectedDocument.deleted || replacing"
              @click="openReplacePanel"
            >
              {{ replacing ? '替换中...' : '替换文件' }}
            </button>

            <button
              v-if="!selectedDocument.deleted"
              class="danger-btn"
              :disabled="isOperator || deleting"
              @click="deleteCurrent"
            >
              {{ deleting ? '删除中...' : '删除文档' }}
            </button>

            <button
              v-else
              class="solid-btn secondary"
              :disabled="isOperator || restoring"
              @click="restoreCurrent"
            >
              {{ restoring ? '恢复中...' : '恢复文档' }}
            </button>
          </div>

          <p v-if="selectedDocument.deleted" class="detail-tip">
            恢复后的文档会自动重建分块，但默认保持“未发布”和“前台隐藏”。
          </p>
          <section data-testid="knowledge-version-panel" class="version-card">
            <div class="table-head">
              <div>
                <p class="panel-label">版本历史</p>
                <strong>{{ versions.length }} 个版本</strong>
              </div>
              <span v-if="versionsLoading" class="summary-pill">加载中</span>
            </div>

            <div v-if="versionsLoading" class="empty-panel">正在加载版本历史...</div>
            <div v-else-if="versions.length === 0" class="empty-panel">当前文档还没有可展示的历史版本。</div>
            <div v-else class="version-layout">
              <div class="version-list">
                <button
                  v-for="version in versions"
                  :key="version.version_id"
                  :data-testid="`knowledge-version-row-${version.version_id}`"
                  class="version-row"
                  :class="{ active: selectedVersion?.version_id === version.version_id }"
                  @click="selectedVersion = version"
                >
                  <strong>V{{ version.version_no }} · {{ version.filename }}</strong>
                  <span>{{ formatVersionAction(version.action) }}</span>
                  <span>{{ version.is_current ? '当前版本' : formatDate(version.created_at) }}</span>
                </button>
              </div>

              <div
                v-if="selectedVersion"
                data-testid="knowledge-version-preview"
                class="version-preview"
              >
                <p class="panel-label">版本快照</p>
                <strong>{{ selectedVersion.filename }}</strong>
                <p>{{ selectedVersion.description || '未设置描述' }}</p>
                <p>{{ formatTags(selectedVersion.tags) }}</p>
                <p>操作类型：{{ formatVersionAction(selectedVersion.action) }}</p>
                <p>文件大小：{{ formatFileSize(selectedVersion.size) }}</p>
                <p>校验值：{{ selectedVersion.checksum }}</p>
                <p>分块数量：{{ selectedVersion.chunk_count || 0 }} 个分块</p>
                <p>来源版本：{{ selectedVersion.source_version_id || '—' }}</p>
                <p>创建时间：{{ formatDate(selectedVersion.created_at) }}</p>
                <p>创建人：{{ selectedVersion.created_by || '未知' }}</p>
                <button
                  data-testid="knowledge-version-rollback"
                  class="solid-btn secondary"
                  :disabled="isOperator || selectedDocument.deleted || rollbacking"
                  @click="rollbackSelectedVersion"
                >
                  {{ rollbacking ? '回滚中...' : '回滚到此版本' }}
                </button>
              </div>
            </div>
          </section>
          </template>
        </div>
      </aside>
    </div>

    <input
      ref="createInput"
      class="hidden-input"
      type="file"
      accept=".txt,.pdf,.docx,.html,.htm,.xlsx"
      @change="handleCreateFile"
    />
    <input
      ref="replaceInput"
      class="hidden-input"
      type="file"
      accept=".txt,.pdf,.docx,.html,.htm,.xlsx"
      @change="handleReplaceFile"
    />
  </section>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { knowledgeAdminApi } from '../../admin-api.js'
import { getAuthUser } from '../../auth/session.js'

const roleOptions = [
  { value: 'user', label: '前台用户' },
  { value: 'operator', label: '运营' },
  { value: 'admin', label: '管理员' },
  { value: 'super_admin', label: '超级管理员' }
]

const documents = ref([])
const selectedDocument = ref(null)
const filters = ref({ keyword: '', status: 'active' })
const createInput = ref(null)
const replaceInput = ref(null)
const loading = ref(false)
const uploading = ref(false)
const replacing = ref(false)
const deleting = ref(false)
const restoring = ref(false)
const saving = ref(false)
const versionsLoading = ref(false)
const rollbacking = ref(false)
const errorMessage = ref('')
const successMessage = ref('')
const versions = ref([])
const selectedVersion = ref(null)
const workspaceGrid = ref(null)
const workspaceHeight = ref('auto')

const isOperator = computed(() => (getAuthUser()?.role || '') === 'operator')
const workspaceStyle = computed(() =>
  workspaceHeight.value === 'auto' ? {} : { '--workspace-height': workspaceHeight.value }
)

function normalizeDocument(doc) {
  const tags = Array.isArray(doc.tags) ? [...doc.tags] : []
  return {
    ...doc,
    description: doc.description || '',
    tags,
    tag_input: tags.join(', '),
    allowed_roles: Array.isArray(doc.allowed_roles) ? [...doc.allowed_roles] : [],
    chunk_count: Number(doc.chunk_count || 0)
  }
}

function setSuccess(message) {
  successMessage.value = message
  errorMessage.value = ''
}

function setError(message) {
  errorMessage.value = message
  successMessage.value = ''
}

function clearMessages() {
  errorMessage.value = ''
  successMessage.value = ''
}

function formatFileSize(bytes) {
  if (!bytes) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatDate(value) {
  if (!value) return '未知时间'
  return new Date(value).toLocaleString('zh-CN')
}

function formatTags(tags) {
  return Array.isArray(tags) && tags.length > 0 ? tags.join('、') : '未设置'
}

function formatVersionAction(action) {
  if (action === 'create') return '创建'
  if (action === 'replace') return '替换'
  if (action === 'rollback') return '回滚'
  return action || '未知'
}

function statusText(doc) {
  if (doc.deleted) return '已删除'
  return doc.published ? '已发布' : '草稿'
}

function statusClass(doc) {
  if (doc.deleted) return 'deleted'
  return doc.published ? 'published' : 'draft'
}

function parseTags(raw) {
  return String(raw || '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
}

function selectDocument(doc) {
  selectedDocument.value = doc || null
}

function syncWorkspaceHeight() {
  if (typeof window === 'undefined') return
  if (window.innerWidth <= 1080 || !workspaceGrid.value) {
    workspaceHeight.value = 'auto'
    return
  }
  const top = workspaceGrid.value.getBoundingClientRect().top
  const availableHeight = Math.max(360, Math.floor(window.innerHeight - top - 24))
  workspaceHeight.value = `${availableHeight}px`
}

function handlePaneWheel(event) {
  const pane = event.currentTarget
  if (!(pane instanceof HTMLElement)) return

  const maxScrollTop = Math.max(0, pane.scrollHeight - pane.clientHeight)
  if (maxScrollTop <= 0) {
    event.preventDefault()
    event.stopPropagation()
    return
  }

  pane.scrollTop = Math.max(0, Math.min(maxScrollTop, pane.scrollTop + event.deltaY))
  event.preventDefault()
  event.stopPropagation()
}

function syncVersionSelection(nextVersions, preferredVersionId = '') {
  const targetId = preferredVersionId || selectedVersion.value?.version_id || ''
  selectedVersion.value =
    nextVersions.find((item) => item.version_id === targetId) ||
    nextVersions[0] ||
    null
}

async function loadVersions(documentId, preferredVersionId = '') {
  if (!documentId) {
    versions.value = []
    selectedVersion.value = null
    return
  }
  versionsLoading.value = true
  try {
    const response = await knowledgeAdminApi.listDocumentVersions(documentId)
    const nextVersions = response.data.versions || []
    versions.value = nextVersions
    syncVersionSelection(nextVersions, preferredVersionId)
  } catch (error) {
    versions.value = []
    selectedVersion.value = null
    setError(error.response?.data?.detail || error.message || '加载版本历史失败')
  } finally {
    versionsLoading.value = false
  }
}

function syncSelection(nextDocuments, preferredDocumentId = '') {
  const targetId = preferredDocumentId || selectedDocument.value?.document_id || ''
  selectedDocument.value =
    nextDocuments.find((doc) => doc.document_id === targetId) ||
    nextDocuments[0] ||
    null
}

async function loadDocuments(preferredDocumentId = '') {
  loading.value = true
  errorMessage.value = ''
  try {
    const response = await knowledgeAdminApi.listDocuments({
      keyword: filters.value.keyword || undefined,
      status: filters.value.status
    })
    const nextDocuments = (response.data.documents || []).map(normalizeDocument)
    documents.value = nextDocuments
    syncSelection(nextDocuments, preferredDocumentId)
  } catch (error) {
    setError(error.response?.data?.detail || error.message || '加载知识文件失败')
  } finally {
    loading.value = false
    await nextTick()
    syncWorkspaceHeight()
  }
}

function toggleRole(role, checked) {
  if (!selectedDocument.value) return
  const next = new Set(selectedDocument.value.allowed_roles)
  if (checked) next.add(role)
  else next.delete(role)
  selectedDocument.value.allowed_roles = roleOptions
    .map((item) => item.value)
    .filter((item) => next.has(item))
}

async function saveCurrent() {
  if (!selectedDocument.value || isOperator.value || selectedDocument.value.deleted) return
  saving.value = true
  try {
    const response = await knowledgeAdminApi.updateDocument(selectedDocument.value.document_id, {
      description: selectedDocument.value.description,
      tags: parseTags(selectedDocument.value.tag_input),
      visible_to_frontend: selectedDocument.value.visible_to_frontend,
      published: selectedDocument.value.published,
      allowed_roles: selectedDocument.value.allowed_roles
    })
    setSuccess(`已更新 ${response.data.filename} 的展示与权限设置`)
    await loadDocuments(response.data.document_id)
    await loadVersions(response.data.document_id)
  } catch (error) {
    setError(error.response?.data?.detail || error.message || '保存文档设置失败')
  } finally {
    saving.value = false
  }
}

function openCreatePanel() {
  if (isOperator.value) return
  createInput.value?.click()
}

async function handleCreateFile(event) {
  const file = event.target?.files?.[0]
  if (!file) return
  uploading.value = true
  try {
    const response = await knowledgeAdminApi.createDocument({
      file,
      description: '',
      tags: [],
      published: false,
      visible_to_frontend: false,
      allowed_roles: ['user', 'operator', 'admin', 'super_admin']
    })
    if (filters.value.status === 'deleted') {
      filters.value.status = 'active'
    }
    setSuccess(`已上传 ${response.data.filename}`)
    await loadDocuments(response.data.document_id)
    await loadVersions(response.data.document_id)
  } catch (error) {
    setError(error.response?.data?.detail || error.message || '上传知识文件失败')
  } finally {
    uploading.value = false
    event.target.value = ''
  }
}

function openReplacePanel() {
  if (!selectedDocument.value || isOperator.value || selectedDocument.value.deleted) return
  replaceInput.value?.click()
}

async function handleReplaceFile(event) {
  const file = event.target?.files?.[0]
  if (!file || !selectedDocument.value) return
  replacing.value = true
  try {
    const response = await knowledgeAdminApi.replaceDocument(selectedDocument.value.document_id, file)
    setSuccess(`已替换 ${response.data.filename}`)
    await loadDocuments(response.data.document_id)
    await loadVersions(response.data.document_id)
  } catch (error) {
    setError(error.response?.data?.detail || error.message || '替换文件失败')
  } finally {
    replacing.value = false
    event.target.value = ''
  }
}

async function deleteCurrent() {
  if (!selectedDocument.value || isOperator.value) return
  if (typeof window !== 'undefined' && typeof window.confirm === 'function') {
    const confirmed = window.confirm(`确认删除 ${selectedDocument.value.filename} 吗？`)
    if (!confirmed) return
  }
  deleting.value = true
  try {
    const response = await knowledgeAdminApi.deleteDocument(selectedDocument.value.document_id)
    setSuccess(`已删除 ${response.data.filename}`)
    await loadDocuments(response.data.document_id)
  } catch (error) {
    setError(error.response?.data?.detail || error.message || '删除文档失败')
  } finally {
    deleting.value = false
  }
}

async function restoreCurrent() {
  if (!selectedDocument.value || isOperator.value) return
  if (typeof window !== 'undefined' && typeof window.confirm === 'function') {
    const confirmed = window.confirm(`确认恢复 ${selectedDocument.value.filename} 吗？恢复后默认保持隐藏和未发布。`)
    if (!confirmed) return
  }
  restoring.value = true
  try {
    const response = await knowledgeAdminApi.restoreDocument(selectedDocument.value.document_id)
    if (filters.value.status === 'deleted') {
      filters.value.status = 'active'
    }
    setSuccess(`已恢复 ${response.data.filename}，默认保持隐藏和未发布`)
    await loadDocuments(response.data.document_id)
  } catch (error) {
    setError(error.response?.data?.detail || error.message || '恢复文档失败')
  } finally {
    restoring.value = false
  }
}

async function rollbackSelectedVersion() {
  if (
    !selectedDocument.value ||
    !selectedVersion.value ||
    isOperator.value ||
    selectedDocument.value.deleted
  ) {
    return
  }
  if (typeof window !== 'undefined' && typeof window.confirm === 'function') {
    const confirmed = window.confirm(
      `确认回滚到版本 ${selectedVersion.value.version_id} 吗？会回滚文件内容、文件名、描述和标签，不会修改发布、显隐、角色和删除状态。`
    )
    if (!confirmed) return
  }
  rollbacking.value = true
  try {
    const response = await knowledgeAdminApi.rollbackDocument(selectedDocument.value.document_id, {
      target_version_id: selectedVersion.value.version_id,
      reason: ''
    })
    setSuccess(`已基于版本 ${response.data.target_version_id} 生成新版本 ${response.data.new_version_id}`)
    await loadDocuments(response.data.document_id)
    await loadVersions(response.data.document_id, response.data.new_version_id)
  } catch (error) {
    setError(error.response?.data?.detail || error.message || '回滚版本失败')
  } finally {
    rollbacking.value = false
  }
}

watch(
  () => selectedDocument.value?.document_id || '',
  async (documentId) => {
    await loadVersions(documentId)
  }
)

watch(
  () => [successMessage.value, errorMessage.value],
  async () => {
    await nextTick()
    syncWorkspaceHeight()
  }
)

onMounted(() => {
  clearMessages()
  loadDocuments()
  syncWorkspaceHeight()
  if (typeof window !== 'undefined') {
    window.addEventListener('resize', syncWorkspaceHeight)
  }
})

onBeforeUnmount(() => {
  if (typeof window !== 'undefined') {
    window.removeEventListener('resize', syncWorkspaceHeight)
  }
})
</script>

<style scoped>
.knowledge-admin-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
  min-height: 0;
}

.page-hero,
.toolbar-card,
.table-card,
.detail-card,
.notice {
  border-radius: 24px;
  border: 1px solid rgba(33, 44, 66, 0.08);
  background: rgba(255, 252, 247, 0.92);
  box-shadow: 0 16px 40px rgba(33, 44, 66, 0.08);
}

.page-hero,
.toolbar-card,
.table-card,
.detail-card {
  padding: 24px;
}

.page-hero,
.toolbar-card,
.table-head,
.detail-head,
.detail-actions {
  display: flex;
  justify-content: space-between;
  gap: 18px;
}

.hero-copy h3,
.detail-head h4,
.metric-card strong,
.table-head strong {
  font-family: Georgia, 'Times New Roman', serif;
}

.hero-copy {
  max-width: 860px;
}

.hero-copy p:last-child,
.detail-id,
.panel-label,
.primary-cell span {
  color: var(--text-secondary);
}

.hero-actions {
  display: grid;
  align-content: start;
  gap: 12px;
}

.mode-pill,
.summary-pill,
.status-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  padding: 10px 14px;
  font-size: 12px;
  font-weight: 600;
}

.mode-pill {
  background: rgba(14, 97, 90, 0.12);
  color: var(--accent);
}

.mode-pill.readonly,
.status-pill.deleted,
.status-pill.hidden {
  background: rgba(196, 111, 36, 0.16);
  color: #97561f;
}

.summary-pill,
.status-pill.soft,
.role-chip,
.toggle-card,
.metric-card {
  background: rgba(246, 241, 233, 0.78);
  color: var(--text-secondary);
}

.status-pill.published {
  background: rgba(14, 97, 90, 0.12);
  color: var(--accent);
}

.status-pill.draft {
  background: rgba(78, 92, 121, 0.12);
  color: #3f4a63;
}

.eyebrow,
.panel-label {
  font-size: 11px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--text-muted);
}

.toolbar-card {
  align-items: end;
  flex-wrap: wrap;
}

.search-field,
.filter-field,
.form-field {
  display: grid;
  gap: 10px;
}

.search-field {
  flex: 1 1 320px;
}

.filter-field {
  min-width: 180px;
}

.search-input,
.filter-select,
.form-field input,
.form-field textarea {
  border: 1px solid rgba(33, 44, 66, 0.12);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.84);
  padding: 12px 14px;
  color: var(--text-primary);
}

.workspace-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(320px, 0.9fr);
  gap: 18px;
  align-items: stretch;
  min-height: 0;
  height: var(--workspace-height, auto);
}

.table-card,
.detail-card {
  min-height: 0;
  height: 100%;
  overflow: hidden;
}

.table-card {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: 18px;
}

.table-shell,
.detail-scroll {
  min-height: 0;
  height: 100%;
  overflow: auto;
  overscroll-behavior: contain;
}

.knowledge-table {
  width: 100%;
  border-collapse: collapse;
}

.knowledge-table th,
.knowledge-table td {
  padding: 14px 12px;
  border-bottom: 1px solid rgba(33, 44, 66, 0.08);
  vertical-align: top;
  text-align: left;
}

.knowledge-table tbody tr {
  cursor: pointer;
  transition: background 0.2s ease, transform 0.2s ease;
}

.knowledge-table tbody tr:hover,
.knowledge-table tbody tr.active {
  background: rgba(246, 241, 233, 0.72);
}

.primary-cell {
  display: grid;
  gap: 6px;
}

.status-stack,
.toggle-grid,
.role-grid,
.detail-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.action-text {
  color: var(--text-secondary);
  white-space: nowrap;
}

.detail-card {
  display: grid;
}

.detail-scroll {
  display: grid;
  gap: 18px;
  align-content: start;
}

.detail-head {
  align-items: start;
}

.detail-status {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  justify-content: flex-end;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.metric-card {
  border-radius: 18px;
  padding: 16px;
  display: grid;
  gap: 8px;
}

.toggle-card,
.role-chip {
  padding: 12px 14px;
  border-radius: 18px;
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.notice {
  padding: 16px 18px;
}

.notice.success {
  background: rgba(14, 97, 90, 0.1);
  color: var(--accent);
}

.notice.error {
  background: rgba(180, 71, 55, 0.1);
  color: #9f3427;
}

.notice.warning {
  background: rgba(196, 111, 36, 0.12);
  color: #8d5d26;
}

.empty-panel {
  min-height: 240px;
  border-radius: 18px;
  background: rgba(246, 241, 233, 0.72);
  color: var(--text-secondary);
  padding: 20px;
  display: grid;
  place-items: center;
  text-align: center;
  line-height: 1.8;
}

.detail-tip {
  color: var(--text-secondary);
  line-height: 1.7;
}

.solid-btn,
.ghost-btn,
.danger-btn {
  border-radius: 999px;
  padding: 12px 18px;
  font-weight: 600;
}

.solid-btn {
  border: none;
  background: var(--accent);
  color: white;
}

.solid-btn.secondary {
  background: #3f4a63;
}

.ghost-btn {
  border: 1px solid rgba(16, 98, 89, 0.18);
  background: rgba(255, 255, 255, 0.72);
}

.danger-btn {
  border: none;
  background: rgba(180, 71, 55, 0.92);
  color: white;
}

.hidden-input {
  display: none;
}

@media (max-width: 1080px) {
  .workspace-grid {
    grid-template-columns: 1fr;
    height: auto;
  }

  .table-card,
  .detail-card {
    height: auto;
    overflow: visible;
  }

  .table-shell,
  .detail-scroll {
    overflow: visible;
  }

  .metric-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 760px) {
  .page-hero,
  .toolbar-card,
  .detail-head,
  .detail-actions {
    flex-direction: column;
  }

  .hero-actions {
    width: 100%;
  }

  .solid-btn,
  .ghost-btn,
  .danger-btn {
    width: 100%;
  }
}
</style>
