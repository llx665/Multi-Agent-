<template>
  <section class="memory-page">
    <article class="hero-card">
      <div>
        <p class="eyebrow">记忆管理</p>
        <h3>面向运营的三层记忆工作台</h3>
        <p>可以按用户搜索、查看上下文快照、修正长期偏好，并在必要时清理上下文或全部记忆。</p>
      </div>
      <button class="ghost-btn" @click="loadUsers" :disabled="loadingUsers">{{ loadingUsers ? '刷新中…' : '刷新用户列表' }}</button>
    </article>

    <div class="workspace-grid">
      <aside class="selector-card">
        <div class="selector-head">
          <div>
            <span class="label">用户索引</span>
            <strong>{{ users.length }} 个用户</strong>
          </div>
          <span class="pill">{{ filteredUsers.length }} 可见</span>
        </div>

        <div class="selector-tools">
          <input v-model.trim="searchText" type="search" placeholder="搜索用户 ID 或用户名" />
        </div>

        <div class="user-list">
          <button
            v-for="user in filteredUsers"
            :key="user.user_id"
            :class="['user-card', { active: selectedUserId === user.user_id }]"
            @click="selectUser(user.user_id)"
          >
            <div class="user-card-top">
              <div>
                <strong>{{ user.username || '未命名用户' }}</strong>
                <p>{{ user.user_id }}</p>
              </div>
              <span :class="['status-tag', user.active_in_memory ? 'online' : 'offline']">
                {{ user.active_in_memory ? '活跃' : '已持久化' }}
              </span>
            </div>
            <div class="user-card-meta">
              <span>{{ user.total_turns }} 轮对话</span>
              <span>{{ user.medium_term_count }} 条摘要</span>
              <span>{{ user.preference_count }} 项偏好</span>
            </div>
          </button>

          <div v-if="!loadingUsers && filteredUsers.length === 0" class="empty-inline">未找到符合条件的记忆用户。</div>
        </div>
      </aside>

      <section class="detail-card">
        <header class="detail-head">
          <div>
            <p class="label">用户详情</p>
            <h4>{{ selectedUserTitle }}</h4>
            <p class="detail-subtitle" v-if="selectedUserSubtitle">{{ selectedUserSubtitle }}</p>
          </div>
          <button class="ghost-btn" @click="loadSelectedUser" :disabled="!selectedUserId || loadingDetail">
            {{ loadingDetail ? '刷新中…' : '刷新详情' }}
          </button>
        </header>

        <p v-if="errorMessage" class="notice error">{{ errorMessage }}</p>
        <p v-if="successMessage" class="notice success">{{ successMessage }}</p>

        <div v-if="!selectedUserId" class="empty-panel">请选择左侧用户查看记忆详情。</div>
        <div v-else-if="loadingDetail" class="empty-panel">正在加载记忆详情…</div>

        <template v-else-if="selectedDetail">
          <section class="stats-grid">
            <article class="stat-card">
              <span class="stat-label">用户 ID</span>
              <strong>{{ selectedDetail.user_id }}</strong>
            </article>
            <article class="stat-card">
              <span class="stat-label">最近会话</span>
              <strong>{{ selectedDetail.context_snapshot?.session_id || '无' }}</strong>
            </article>
            <article class="stat-card">
              <span class="stat-label">短期记忆</span>
              <strong>{{ shortTermCount }}</strong>
            </article>
            <article class="stat-card">
              <span class="stat-label">长期偏好</span>
              <strong>{{ preferenceEntries.length }}</strong>
            </article>
          </section>

          <section class="actions-grid">
            <article class="panel">
              <div class="panel-head">
                <div>
                  <h5>记忆操作</h5>
                  <p>清理上下文快照或删除该用户全部长期记忆。</p>
                </div>
                <div class="panel-actions">
                  <button class="ghost-btn danger" @click="clearContextMemory" :disabled="actionLoading">清理上下文</button>
                  <button class="solid-btn danger" @click="clearAllMemory" :disabled="actionLoading">清理全部记忆</button>
                </div>
              </div>
            </article>

            <article class="panel">
              <div class="panel-head compact">
                <div>
                  <h5>偏好修正</h5>
                  <p>将新的偏好写入长期记忆，并同步到上下文元数据。</p>
                </div>
              </div>
              <div class="editor-grid">
                <label>
                  偏好键
                  <input v-model.trim="preferenceKey" type="text" placeholder="例如：customer_type" />
                </label>
                <label>
                  置信度
                  <input v-model.number="preferenceConfidence" type="number" min="0" max="1" step="0.1" />
                </label>
              </div>
              <label class="editor-block">
                偏好值
                <textarea v-model="preferenceValue" rows="4" placeholder="输入文本或 JSON"></textarea>
              </label>
              <div class="editor-actions">
                <button class="solid-btn" @click="savePreference" :disabled="actionLoading || !preferenceKey">保存偏好</button>
              </div>
            </article>
          </section>

          <section class="content-grid">
            <article class="panel">
              <div class="panel-head compact">
                <div>
                  <h5>长期偏好</h5>
                  <p>来自长期记忆画像的偏好条目。</p>
                </div>
              </div>
              <div v-if="preferenceEntries.length === 0" class="empty-inline">暂无长期偏好。</div>
              <div v-else class="kv-list">
                <div v-for="entry in preferenceEntries" :key="entry.key" class="kv-row">
                  <div>
                    <strong>{{ entry.key }}</strong>
                    <p>{{ formatPreferenceSource(entry.meta?.source) }} / 置信度 {{ entry.meta?.confidence ?? '无' }}</p>
                  </div>
                  <code>{{ formatInlineValue(entry.value) }}</code>
                </div>
              </div>
            </article>

            <article class="panel">
              <div class="panel-head compact">
                <div>
                  <h5>上下文元数据</h5>
                  <p>当前持久化上下文中的元数据快照。</p>
                </div>
              </div>
              <pre class="json-block">{{ formatJson(selectedDetail.context_snapshot?.metadata || {}) }}</pre>
            </article>
          </section>

          <section class="content-grid">
            <article class="panel">
              <div class="panel-head compact">
                <div>
                  <h5>最近对话</h5>
                  <p>最近持久化的 20 条对话内容。</p>
                </div>
              </div>
              <div v-if="recentTurns.length === 0" class="empty-inline">暂无持久化对话。</div>
              <div v-else class="turn-list">
                <div v-for="turn in recentTurns" :key="turn.timestamp + turn.role + turn.content.slice(0, 12)" class="turn-card">
                  <div class="turn-meta">
                    <span class="turn-role">{{ formatTurnRole(turn.role) }}</span>
                    <span>{{ formatDateTime(turn.timestamp) }}</span>
                    <span v-if="turn.intent">{{ turn.intent }}</span>
                  </div>
                  <p>{{ turn.content }}</p>
                </div>
              </div>
            </article>

            <article class="panel">
              <div class="panel-head compact">
                <div>
                  <h5>中期摘要</h5>
                  <p>对话压缩后的摘要列表。</p>
                </div>
              </div>
              <div v-if="mediumMemories.length === 0" class="empty-inline">暂无中期摘要。</div>
              <div v-else class="memory-list">
                <div v-for="memory in mediumMemories" :key="memory.timestamp + memory.summary" class="memory-card">
                  <strong>{{ memory.summary }}</strong>
                  <p>{{ memory.discussed_topics?.join(' / ') || '无主题标签' }}</p>
                  <span>{{ formatDateTime(memory.timestamp) }}</span>
                </div>
              </div>
            </article>
          </section>
        </template>
      </section>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'

import { memoryAdminApi } from '../../admin-api.js'

const users = ref([])
const selectedUserId = ref('')
const selectedDetail = ref(null)
const searchText = ref('')
const loadingUsers = ref(false)
const loadingDetail = ref(false)
const actionLoading = ref(false)
const errorMessage = ref('')
const successMessage = ref('')
const preferenceKey = ref('')
const preferenceValue = ref('')
const preferenceConfidence = ref(1)

const filteredUsers = computed(() => {
  const keyword = searchText.value.trim().toLowerCase()
  if (!keyword) {
    return users.value
  }
  return users.value.filter((user) => {
    const userId = (user.user_id || '').toLowerCase()
    const username = (user.username || '').toLowerCase()
    return userId.includes(keyword) || username.includes(keyword)
  })
})

const selectedUserRecord = computed(() => {
  return selectedDetail.value || users.value.find((item) => item.user_id === selectedUserId.value) || null
})

const selectedUserTitle = computed(() => {
  const user = selectedUserRecord.value
  if (!user) return '请选择要查看记忆的用户'
  return user.username || user.user_id
})

const selectedUserSubtitle = computed(() => {
  const user = selectedUserRecord.value
  if (!user) return ''
  if (user.username) {
    return `用户 ID：${user.user_id} / 用户名：${user.username}`
  }
  return `用户 ID：${user.user_id}`
})

const shortTermCount = computed(() => selectedDetail.value?.context_snapshot?.three_tier_summary?.stats?.short_term_turns || 0)
const recentTurns = computed(() => selectedDetail.value?.context_snapshot?.turn_history?.slice(-20) || [])
const mediumMemories = computed(() => selectedDetail.value?.context_snapshot?.medium_term?.compressed_memories?.slice(-10) || [])
const preferenceEntries = computed(() => {
  const profile = selectedDetail.value?.long_term_profile || {}
  const preferences = profile.preferences || {}
  const meta = profile.preference_meta || {}
  return Object.keys(preferences).map((key) => ({
    key,
    value: preferences[key],
    meta: meta[key] || null
  }))
})

function setError(message) {
  errorMessage.value = message
  successMessage.value = ''
}

function setSuccess(message) {
  successMessage.value = message
  errorMessage.value = ''
}

function resetMessages() {
  errorMessage.value = ''
  successMessage.value = ''
}

function formatUserLabel(user) {
  if (!user) return ''
  if (user.username) return `${user.username}（${user.user_id}）`
  return user.user_id
}

function formatPreferenceSource(source) {
  const labels = {
    admin_override: '后台修正',
    llm_inference: '模型推断',
    explicit_feedback: '显式反馈',
    user_input: '用户输入'
  }
  return labels[source] || source || '未知来源'
}

function formatTurnRole(role) {
  const labels = {
    user: '用户',
    human: '用户',
    assistant: '助手',
    ai: '助手',
    system: '系统',
    tool: '工具'
  }
  return labels[role] || role
}

async function loadUsers() {
  loadingUsers.value = true
  resetMessages()
  try {
    const response = await memoryAdminApi.listUsers()
    users.value = response.data.users || []
    if (!selectedUserId.value && users.value.length > 0) {
      await selectUser(users.value[0].user_id)
    }
  } catch (error) {
    setError(error.response?.data?.detail || error.message || '加载用户列表失败')
  } finally {
    loadingUsers.value = false
  }
}

async function loadSelectedUser() {
  if (!selectedUserId.value) return
  loadingDetail.value = true
  resetMessages()
  try {
    const response = await memoryAdminApi.getUser(selectedUserId.value)
    selectedDetail.value = response.data
  } catch (error) {
    setError(error.response?.data?.detail || error.message || '加载记忆详情失败')
  } finally {
    loadingDetail.value = false
  }
}

async function selectUser(userId) {
  selectedUserId.value = userId
  await loadSelectedUser()
}

function parsePreferenceValue(raw) {
  const trimmed = raw.trim()
  if (!trimmed) return ''
  try {
    return JSON.parse(trimmed)
  } catch {
    return raw
  }
}

async function savePreference() {
  if (!selectedUserId.value || !preferenceKey.value) return
  actionLoading.value = true
  resetMessages()
  try {
    await memoryAdminApi.updatePreference(selectedUserId.value, {
      key: preferenceKey.value,
      value: parsePreferenceValue(preferenceValue.value),
      confidence: preferenceConfidence.value
    })
    await Promise.all([loadUsers(), loadSelectedUser()])
    setSuccess('偏好已写入长期记忆，并同步到上下文元数据。')
  } catch (error) {
    setError(error.response?.data?.detail || error.message || '保存偏好失败')
  } finally {
    actionLoading.value = false
  }
}

async function clearContextMemory() {
  if (!selectedUserId.value) return
  const label = formatUserLabel(selectedUserRecord.value)
  if (!window.confirm(`确认清理 ${label} 的上下文快照吗？`)) return
  actionLoading.value = true
  resetMessages()
  try {
    await memoryAdminApi.clearContext(selectedUserId.value)
    await Promise.all([loadUsers(), loadSelectedUser()])
    setSuccess('上下文快照已清理。')
  } catch (error) {
    setError(error.response?.data?.detail || error.message || '清理上下文失败')
  } finally {
    actionLoading.value = false
  }
}

async function clearAllMemory() {
  if (!selectedUserId.value) return
  const label = formatUserLabel(selectedUserRecord.value)
  if (!window.confirm(`确认清理 ${label} 的全部记忆吗？`)) return
  actionLoading.value = true
  resetMessages()
  try {
    const removedUserId = selectedUserId.value
    await memoryAdminApi.clearAll(removedUserId)
    await loadUsers()
    if (selectedUserId.value === removedUserId) {
      selectedUserId.value = ''
      selectedDetail.value = null
    }
    setSuccess('用户的长期记忆与上下文快照已清理。')
  } catch (error) {
    setError(error.response?.data?.detail || error.message || '清理全部记忆失败')
  } finally {
    actionLoading.value = false
  }
}

function formatJson(value) {
  return JSON.stringify(value, null, 2)
}

function formatInlineValue(value) {
  return typeof value === 'string' ? value : JSON.stringify(value)
}

function formatDateTime(value) {
  if (!value) return '无'
  return new Date(value).toLocaleString('zh-CN')
}

onMounted(() => {
  loadUsers()
})
</script>

<style scoped>
.memory-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.hero-card,
.selector-card,
.detail-card,
.panel,
.stat-card {
  background: rgba(255, 252, 247, 0.84);
  border: 1px solid rgba(33, 44, 66, 0.08);
  box-shadow: 0 16px 40px rgba(33, 44, 66, 0.08);
}

.hero-card,
.selector-card,
.detail-card,
.panel {
  border-radius: 24px;
}

.hero-card {
  padding: 24px;
  display: flex;
  justify-content: space-between;
  gap: 14px;
}

.workspace-grid {
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr);
  gap: 18px;
}

.selector-card,
.detail-card {
  padding: 20px;
}

.selector-card {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.selector-head,
.user-card-top,
.detail-head,
.panel-head,
.panel-actions,
.editor-grid,
.editor-actions,
.user-card-meta,
.stats-grid,
.turn-meta {
  display: flex;
}

.selector-head,
.detail-head,
.panel-head {
  justify-content: space-between;
  gap: 12px;
}

.selector-head,
.user-card-top,
.panel-head {
  align-items: flex-start;
}

.detail-head {
  align-items: center;
}

.selector-tools input,
.editor-grid input,
.editor-block textarea {
  width: 100%;
  padding: 12px 14px;
  border-radius: 14px;
  border: 1px solid rgba(33, 44, 66, 0.12);
  background: rgba(255, 255, 255, 0.92);
}

.user-list,
.kv-list,
.turn-list,
.memory-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.user-card {
  padding: 14px;
  border-radius: 18px;
  border: 1px solid rgba(33, 44, 66, 0.08);
  background: rgba(255, 255, 255, 0.72);
  text-align: left;
}

.user-card.active {
  background: linear-gradient(135deg, rgba(16, 98, 89, 0.12), rgba(196, 111, 36, 0.12));
  border-color: rgba(16, 98, 89, 0.18);
}

.user-card p,
.user-card-meta,
.detail-subtitle,
.notice,
.empty-panel,
.empty-inline,
.panel p,
.turn-card p,
.memory-card p {
  color: var(--text-secondary);
}

.user-card p,
.detail-subtitle,
.panel p,
.turn-card p,
.memory-card p {
  margin-top: 6px;
}

.user-card-meta,
.turn-meta {
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 10px;
  font-size: 12px;
}

.pill,
.status-tag {
  padding: 5px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
}

.pill {
  background: rgba(16, 98, 89, 0.08);
  color: var(--text-primary);
}

.status-tag.online {
  background: rgba(15, 128, 87, 0.12);
  color: #0f7a59;
}

.status-tag.offline {
  background: rgba(124, 141, 163, 0.12);
  color: #5b6776;
}

.detail-card {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.stats-grid,
.actions-grid,
.content-grid,
.editor-grid {
  gap: 14px;
}

.stats-grid {
  flex-wrap: wrap;
}

.actions-grid,
.content-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.stat-card {
  flex: 1 1 180px;
  padding: 18px;
  border-radius: 20px;
}

.stat-label,
.label,
.eyebrow {
  font-size: 11px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--text-muted);
}

h3,
h4,
h5 {
  margin-top: 10px;
  font-family: Georgia, 'Times New Roman', serif;
}

h3 {
  font-size: 30px;
}

h4 {
  font-size: 26px;
}

h5 {
  font-size: 22px;
}

.hero-card p,
.empty-panel,
.empty-inline,
.notice,
.panel p,
.json-block,
code,
.memory-card span {
  line-height: 1.7;
}

.panel {
  padding: 20px;
}

.panel-head.compact {
  margin-bottom: 12px;
}

.panel-actions,
.editor-actions {
  gap: 10px;
}

.editor-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

label,
.editor-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
  color: var(--text-secondary);
  font-size: 13px;
}

.editor-block {
  margin-top: 12px;
}

.kv-row,
.turn-card,
.memory-card {
  padding: 14px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.76);
  border: 1px solid rgba(33, 44, 66, 0.08);
}

.kv-row {
  display: flex;
  justify-content: space-between;
  gap: 16px;
}

code,
.json-block {
  font-family: 'Consolas', 'Courier New', monospace;
}

code {
  max-width: 50%;
  white-space: pre-wrap;
  word-break: break-word;
}

.turn-role {
  color: #0f7a59;
  font-weight: 700;
}

.json-block {
  margin: 0;
  padding: 16px;
  border-radius: 18px;
  background: #102632;
  color: #e3f4ff;
  overflow: auto;
}

.notice {
  padding: 12px 14px;
  border-radius: 16px;
}

.notice.error {
  background: #fef0f0;
  color: #b42318;
}

.notice.success {
  background: #edfdf7;
  color: #0f7a59;
}

.empty-panel,
.empty-inline {
  padding: 22px;
  border-radius: 18px;
  border: 1px dashed rgba(33, 44, 66, 0.12);
  background: rgba(255, 255, 255, 0.56);
}

.ghost-btn,
.solid-btn {
  padding: 12px 16px;
  border-radius: 999px;
  font-weight: 600;
}

.ghost-btn {
  border: 1px solid rgba(16, 98, 89, 0.16);
  background: rgba(255, 255, 255, 0.82);
}

.solid-btn {
  border: none;
  background: linear-gradient(135deg, #0f7a59, #17475a);
  color: #fff;
}

.ghost-btn.danger {
  border-color: rgba(186, 24, 27, 0.18);
  color: #b42318;
}

.solid-btn.danger {
  background: linear-gradient(135deg, #b42318, #d04c35);
}

@media (max-width: 1100px) {
  .workspace-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 900px) {
  .hero-card,
  .detail-head,
  .panel-head,
  .panel-actions,
  .kv-row {
    flex-direction: column;
    align-items: flex-start;
  }

  .actions-grid,
  .content-grid,
  .editor-grid {
    grid-template-columns: 1fr;
  }

  code {
    max-width: 100%;
  }
}
</style>
