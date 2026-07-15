<template>
  <section class="knowledge-shell">
    <article class="hero-card">
      <div>
        <p class="eyebrow">知识库</p>
        <h3>前台只读知识库</h3>
        <p>{{ knowledgePolicy.intro_text }}</p>
        <p class="readonly-note">{{ knowledgePolicy.readonly_notice }}</p>
      </div>
      <button class="ghost-btn" @click="loadDocuments" :disabled="loading">
        {{ loading ? '刷新中...' : '刷新列表' }}
      </button>
    </article>

    <p v-if="errorMessage" class="notice error">{{ errorMessage }}</p>

    <div class="workspace-grid">
      <aside class="list-card">
        <div class="list-head">
          <div>
            <span class="label">可访问文件</span>
            <strong>{{ documents.length }} 份文档</strong>
          </div>
          <span class="pill">只读</span>
        </div>

        <div v-if="loading && documents.length === 0" class="empty-inline">正在加载知识文件...</div>
        <div v-else-if="documents.length === 0" class="empty-inline">{{ knowledgePolicy.empty_state_text }}</div>

        <button
          v-for="doc in documents"
          :key="doc.id"
          :class="['doc-item', { active: selectedDoc?.id === doc.id }]"
          @click="selectDocument(doc)"
        >
          <div>
            <strong>{{ doc.filename }}</strong>
            <p>{{ formatFileSize(doc.size) }} · {{ doc.chunk_count || 0 }} 个分块 · {{ doc.file_type }}</p>
          </div>
          <span>{{ formatDate(doc.update_time) }}</span>
        </button>
      </aside>

      <section class="preview-card">
        <header class="preview-head">
          <div>
            <p class="label">文档预览</p>
            <h4>{{ selectedDoc?.filename || '请选择文档' }}</h4>
            <p v-if="selectedDoc" class="preview-meta">
              更新时间 {{ formatDate(selectedDoc.update_time) }} · {{ formatFileSize(selectedDoc.size) }}
            </p>
          </div>
        </header>

        <div v-if="selectedDoc && knowledgePolicy.show_document_metrics" class="metric-strip">
          <span class="metric-pill">文件类型：{{ selectedDoc.file_type }}</span>
          <span class="metric-pill">分块数量：{{ selectedDoc.chunk_count || 0 }} 个分块</span>
          <span class="metric-pill">文档 ID：{{ selectedDoc.id }}</span>
        </div>

        <div v-if="!selectedDoc" class="empty-panel">从左侧选择文档后即可查看内容。</div>
        <div v-else-if="loadingContent" class="empty-panel">正在加载文档内容...</div>
        <pre v-else class="content-block">{{ selectedContent || '该文档暂无可读内容。' }}</pre>
      </section>
    </div>
  </section>
</template>

<script setup>
import { onMounted, ref } from 'vue'

import { knowledgeBaseApi } from '../api/index.js'

const defaultKnowledgePolicy = () => ({
  intro_text: '这里仅展示当前账号角色允许访问且已发布的知识文件。',
  empty_state_text: '当前角色暂无可访问的知识文件。',
  readonly_notice: '知识文件的编辑、发布和访问规则统一在后台维护。',
  show_document_metrics: true
})

const documents = ref([])
const selectedDoc = ref(null)
const selectedContent = ref('')
const knowledgePolicy = ref(defaultKnowledgePolicy())
const loading = ref(false)
const loadingContent = ref(false)
const errorMessage = ref('')

function setError(message) {
  errorMessage.value = message
}

function clearError() {
  errorMessage.value = ''
}

async function loadDocuments() {
  loading.value = true
  clearError()
  try {
    const [documentsResponse, paramsResponse] = await Promise.all([
      knowledgeBaseApi.getDocuments(),
      knowledgeBaseApi.getParams()
    ])
    documents.value = documentsResponse.data.documents || []
    knowledgePolicy.value = paramsResponse.data.frontend_policy?.knowledge_base || defaultKnowledgePolicy()
    if (documents.value.length > 0) {
      const stillSelected = documents.value.find((doc) => doc.id === selectedDoc.value?.id)
      await selectDocument(stillSelected || documents.value[0])
    } else {
      selectedDoc.value = null
      selectedContent.value = ''
    }
  } catch (error) {
    setError(error.response?.data?.detail || error.message || '加载知识文件失败')
  } finally {
    loading.value = false
  }
}

async function selectDocument(doc) {
  selectedDoc.value = doc
  loadingContent.value = true
  clearError()
  try {
    const response = await knowledgeBaseApi.getDocument(doc.id)
    selectedContent.value = response.data.content || ''
  } catch (error) {
    selectedContent.value = ''
    setError(error.response?.data?.detail || error.message || '加载文档内容失败')
  } finally {
    loadingContent.value = false
  }
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

onMounted(() => {
  loadDocuments()
})
</script>

<style scoped>
.knowledge-shell {
  display: grid;
  gap: 18px;
}

.hero-card,
.list-card,
.preview-card {
  background: rgba(255, 252, 247, 0.92);
  border: 1px solid rgba(33, 44, 66, 0.08);
  border-radius: 24px;
  box-shadow: 0 16px 40px rgba(33, 44, 66, 0.08);
}

.hero-card {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  padding: 24px;
}

.workspace-grid {
  display: grid;
  grid-template-columns: minmax(280px, 360px) minmax(0, 1fr);
  gap: 18px;
}

.list-card,
.preview-card {
  padding: 22px;
}

.list-head,
.preview-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  margin-bottom: 16px;
}

.eyebrow,
.label {
  font-size: 11px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--text-muted);
}

.pill {
  padding: 8px 12px;
  border-radius: 999px;
  background: rgba(14, 97, 90, 0.1);
  color: var(--accent);
  font-size: 12px;
  font-weight: 600;
}

.readonly-note {
  margin-top: 10px;
  color: var(--text-secondary);
}

.metric-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 16px;
}

.metric-pill {
  display: inline-flex;
  align-items: center;
  padding: 10px 12px;
  border-radius: 999px;
  background: rgba(246, 241, 233, 0.78);
  color: var(--text-secondary);
  font-size: 12px;
}

.doc-item {
  width: 100%;
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 16px;
  margin-bottom: 12px;
  border: 1px solid rgba(33, 44, 66, 0.08);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.8);
  text-align: left;
}

.doc-item.active {
  border-color: rgba(14, 97, 90, 0.3);
  box-shadow: 0 12px 24px rgba(14, 97, 90, 0.08);
}

.doc-item strong,
.preview-head h4,
.hero-card h3 {
  font-family: Georgia, 'Times New Roman', serif;
}

.doc-item p,
.hero-card p,
.preview-meta {
  margin-top: 8px;
  color: var(--text-secondary);
  line-height: 1.7;
}

.content-block,
.empty-panel,
.empty-inline {
  min-height: 240px;
  padding: 20px;
  border-radius: 18px;
  background: rgba(246, 241, 233, 0.72);
  color: var(--text-secondary);
  line-height: 1.8;
  white-space: pre-wrap;
}

.content-block {
  font-family: 'Fira Code', 'Cascadia Code', monospace;
  overflow: auto;
}

.notice {
  padding: 14px 16px;
  border-radius: 16px;
}

.notice.error {
  background: rgba(180, 71, 55, 0.1);
  color: #9f3427;
}

.ghost-btn {
  padding: 12px 18px;
  border-radius: 999px;
  border: 1px solid rgba(16, 98, 89, 0.18);
  background: rgba(255, 255, 255, 0.72);
}

@media (max-width: 960px) {
  .hero-card,
  .workspace-grid {
    grid-template-columns: 1fr;
  }

  .hero-card {
    flex-direction: column;
  }
}
</style>
