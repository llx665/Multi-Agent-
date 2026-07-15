<template>
  <section class="users-page">
    <article class="hero-card">
      <div>
        <p class="eyebrow">账号管理</p>
        <h3>统一管理后台账号状态与角色</h3>
        <p>支持账号筛选、详情查看、状态切换与角色更新。</p>
      </div>
      <button class="ghost-btn" @click="loadUsers" :disabled="loading">{{ loading ? '刷新中…' : '刷新列表' }}</button>
    </article>

    <article class="filters-card">
      <label>
        搜索账号
        <input v-model.trim="filters.q" placeholder="用户名 / 用户 ID" />
      </label>
      <label>
        角色
        <select v-model="filters.role">
          <option value="">全部</option>
          <option value="user">普通用户</option>
          <option value="operator">运营员</option>
          <option value="admin">管理员</option>
          <option value="super_admin">超级管理员</option>
        </select>
      </label>
      <label>
        状态
        <select v-model="filters.status">
          <option value="">全部</option>
          <option value="active">启用</option>
          <option value="disabled">停用</option>
        </select>
      </label>
      <button class="ghost-btn" @click="applyFilters">应用筛选</button>
    </article>

    <article class="workspace-card">
      <p v-if="errorMessage" class="error-text">{{ errorMessage }}</p>
      <div class="workspace-grid">
        <section class="list-panel">
          <header class="panel-head">
            <h4>账号列表</h4>
            <span>{{ users.length }} 个账号</span>
          </header>
          <p v-if="!users.length" class="empty-text">当前筛选条件下暂无账号。</p>
          <ul v-else class="user-list">
            <li v-for="item in users" :key="item.user_id">
              <button
                class="user-item"
                :class="{ active: selectedUserId === item.user_id }"
                :data-testid="`user-list-item-${item.user_id}`"
                @click="selectUser(item.user_id)"
              >
                <div>
                  <strong>{{ item.username || '未命名账号' }}</strong>
                  <p class="mono">{{ item.user_id }}</p>
                </div>
                <div class="meta">
                  <span :data-testid="`user-list-status-${item.user_id}`">{{ statusLabel(item.status) }}</span>
                  <span>{{ roleLabel(item.role) }}</span>
                </div>
              </button>
            </li>
          </ul>
        </section>

        <section class="detail-panel" data-testid="user-detail-panel">
          <header class="panel-head">
            <h4>账号详情</h4>
            <span v-if="selectedUserDetail">{{ selectedUserDetail.username || selectedUserDetail.user_id }}</span>
          </header>

          <p v-if="loadingDetail" class="empty-text">详情加载中…</p>
          <p v-else-if="detailErrorMessage" class="error-text detail-error" data-testid="detail-load-error">{{ detailErrorMessage }}</p>
          <p v-else-if="!selectedUserDetail" class="empty-text">请先在左侧选择账号。</p>
          <template v-else>
            <dl class="detail-grid">
              <div>
                <dt>用户 ID</dt>
                <dd class="mono" data-testid="detail-user-id">{{ selectedUserDetail.user_id }}</dd>
              </div>
              <div>
                <dt>用户名</dt>
                <dd>{{ selectedUserDetail.username || '未命名账号' }}</dd>
              </div>
              <div>
                <dt>角色</dt>
                <dd data-testid="detail-role">{{ roleLabel(selectedUserDetail.role) }}</dd>
              </div>
              <div>
                <dt>状态</dt>
                <dd data-testid="detail-status">{{ statusLabel(selectedUserDetail.status) }}</dd>
              </div>
              <div>
                <dt>创建时间</dt>
                <dd>{{ formatTime(selectedUserDetail.created_at) }}</dd>
              </div>
              <div>
                <dt>更新时间</dt>
                <dd>{{ formatTime(selectedUserDetail.updated_at) }}</dd>
              </div>
              <div>
                <dt>最近登录</dt>
                <dd>{{ formatTime(selectedUserDetail.last_login_at) }}</dd>
              </div>
              <div>
                <dt>密码更新时间</dt>
                <dd>{{ formatTime(selectedUserDetail.password_updated_at) }}</dd>
              </div>
            </dl>

            <section class="action-section">
              <h5>状态操作</h5>
              <button
                class="ghost-btn"
                data-testid="status-toggle-btn"
                :disabled="!canToggleStatus"
                @click="toggleStatus"
              >
                {{ updatingStatus ? '提交中…' : selectedUserDetail.status === 'active' ? '停用账号' : '启用账号' }}
              </button>
              <p v-if="statusDisabledReason" class="hint-text" data-testid="status-disabled-hint">{{ statusDisabledReason }}</p>
            </section>

            <section v-if="isSuperAdmin" class="action-section">
              <h5>角色编辑</h5>
              <select data-testid="role-editor" v-model="roleDraft" :disabled="!canEditSelectedRole">
                <option value="user">普通用户</option>
                <option value="operator">运营员</option>
                <option value="admin">管理员</option>
                <option value="super_admin">超级管理员</option>
              </select>
              <button
                class="ghost-btn"
                data-testid="role-save-btn"
                :disabled="!canSaveRole"
                @click="saveRole"
              >
                {{ savingRole ? '保存中…' : '保存角色' }}
              </button>
              <p v-if="!canEditSelectedRole" class="hint-text">仅可修改其他账号角色。</p>
            </section>
          </template>
        </section>
      </div>
    </article>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'

import { userAdminApi } from '../../admin-api.js'
import { getAuthUser } from '../../auth/session.js'

const currentUser = getAuthUser() || {}
const currentRole = currentUser.role || ''
const isSuperAdmin = computed(() => currentRole === 'super_admin')
const canManageStatus = computed(() => ['admin', 'super_admin'].includes(currentRole))

const filters = ref({ q: '', role: '', status: '' })
const users = ref([])
const selectedUserId = ref('')
const selectedUserDetail = ref(null)
const roleDraft = ref('user')

const loading = ref(false)
const loadingDetail = ref(false)
const updatingStatus = ref(false)
const savingRole = ref(false)
const errorMessage = ref('')
const detailErrorMessage = ref('')
const detailRequestId = ref(0)

const statusDisabledReason = computed(() => {
  if (loadingDetail.value || !selectedUserDetail.value) {
    return '详情加载中，暂不可操作'
  }
  if (!canManageStatus.value) {
    return '当前角色无状态操作权限'
  }
  if (currentRole === 'admin') {
    if (selectedUserDetail.value.user_id === currentUser.user_id) {
      return '管理员不能操作自己的账号状态'
    }
    if (['admin', 'super_admin'].includes(selectedUserDetail.value.role)) {
      return '管理员不能操作管理员或超管账号'
    }
  }
  return ''
})

const canToggleStatus = computed(() => !statusDisabledReason.value && !updatingStatus.value && !loading.value)

const canEditSelectedRole = computed(() => {
  if (!isSuperAdmin.value || loadingDetail.value || !selectedUserDetail.value) {
    return false
  }
  return selectedUserDetail.value.user_id !== currentUser.user_id
})

const canSaveRole = computed(() => {
  if (!canEditSelectedRole.value || !selectedUserDetail.value || savingRole.value) {
    return false
  }
  return roleDraft.value !== selectedUserDetail.value.role
})

function formatTime(value) {
  return value || '—'
}

function statusLabel(status) {
  if (status === 'active') return '启用'
  if (status === 'disabled') return '停用'
  return status || '—'
}

function roleLabel(role) {
  const labelMap = {
    user: '普通用户',
    operator: '运营员',
    admin: '管理员',
    super_admin: '超级管理员'
  }
  return labelMap[role] || role || '—'
}

async function loadUserDetail(userId) {
  const requestId = ++detailRequestId.value
  selectedUserDetail.value = null
  roleDraft.value = 'user'
  detailErrorMessage.value = ''

  if (!userId) {
    loadingDetail.value = false
    return
  }

  loadingDetail.value = true
  try {
    const response = await userAdminApi.getUser(userId)
    if (requestId !== detailRequestId.value) {
      return
    }
    selectedUserDetail.value = response.data || null
    roleDraft.value = selectedUserDetail.value?.role || 'user'
  } catch (error) {
    if (requestId !== detailRequestId.value) {
      return
    }
    detailErrorMessage.value = error.response?.data?.detail || '加载账号详情失败，请点击左侧账号重试'
  } finally {
    if (requestId === detailRequestId.value) {
      loadingDetail.value = false
    }
  }
}

async function loadUsers(options = {}) {
  const { preserveSelection = true } = options
  loading.value = true
  errorMessage.value = ''
  try {
    const response = await userAdminApi.listUsers(filters.value)
    users.value = response.data.users || []

    const previousId = preserveSelection ? selectedUserId.value : ''
    const hasPrevious = users.value.some((item) => item.user_id === previousId)
    selectedUserId.value = hasPrevious ? previousId : users.value[0]?.user_id || ''
    await loadUserDetail(selectedUserId.value)
  } catch (error) {
    errorMessage.value = error.response?.data?.detail || error.message || '加载账号列表失败'
  } finally {
    loading.value = false
  }
}

async function applyFilters() {
  await loadUsers({ preserveSelection: false })
}

async function selectUser(userId) {
  if (
    selectedUserId.value === userId &&
    selectedUserDetail.value &&
    !detailErrorMessage.value
  ) {
    return
  }
  selectedUserId.value = userId
  await loadUserDetail(userId)
}

async function toggleStatus() {
  if (!selectedUserDetail.value || !canToggleStatus.value) {
    return
  }
  const targetStatus = selectedUserDetail.value.status === 'active' ? 'disabled' : 'active'
  updatingStatus.value = true
  errorMessage.value = ''
  try {
    await userAdminApi.updateStatus(selectedUserDetail.value.user_id, targetStatus)
    await loadUsers({ preserveSelection: true })
  } catch (error) {
    errorMessage.value = error.response?.data?.detail || error.message || '更新账号状态失败'
  } finally {
    updatingStatus.value = false
  }
}

async function saveRole() {
  if (!selectedUserDetail.value || !canSaveRole.value) {
    return
  }
  savingRole.value = true
  errorMessage.value = ''
  try {
    await userAdminApi.updateRole(selectedUserDetail.value.user_id, roleDraft.value)
    await loadUsers({ preserveSelection: true })
  } catch (error) {
    errorMessage.value = error.response?.data?.detail || error.message || '更新角色失败'
  } finally {
    savingRole.value = false
  }
}

onMounted(() => {
  loadUsers({ preserveSelection: false })
})
</script>

<style scoped>
.users-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.hero-card,
.filters-card,
.workspace-card {
  padding: 24px;
  border-radius: 24px;
  background: rgba(255, 252, 247, 0.84);
  border: 1px solid rgba(33, 44, 66, 0.08);
  box-shadow: 0 16px 40px rgba(33, 44, 66, 0.08);
}

.hero-card,
.filters-card {
  display: flex;
  justify-content: space-between;
  gap: 14px;
}

.filters-card {
  align-items: flex-end;
  flex-wrap: wrap;
}

.workspace-grid {
  display: grid;
  grid-template-columns: minmax(280px, 1fr) minmax(380px, 1.4fr);
  gap: 14px;
}

.list-panel,
.detail-panel {
  padding: 18px;
  border-radius: 18px;
  border: 1px solid rgba(33, 44, 66, 0.08);
  background: rgba(255, 255, 255, 0.72);
}

.panel-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 12px;
}

.panel-head h4 {
  margin: 0;
}

.panel-head span {
  font-size: 12px;
  color: var(--text-muted);
}

.user-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.user-item {
  width: 100%;
  border: 1px solid rgba(33, 44, 66, 0.1);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.92);
  padding: 12px;
  text-align: left;
  display: flex;
  justify-content: space-between;
  gap: 10px;
}

.user-item.active {
  border-color: rgba(16, 98, 89, 0.4);
  box-shadow: 0 0 0 1px rgba(16, 98, 89, 0.18);
}

.user-item strong {
  display: block;
}

.user-item .mono {
  margin-top: 4px;
}

.meta {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
  color: var(--text-muted);
  font-size: 12px;
}

.detail-grid {
  margin: 0;
  display: grid;
  grid-template-columns: repeat(2, minmax(140px, 1fr));
  gap: 12px;
}

.detail-grid dt {
  font-size: 12px;
  color: var(--text-muted);
}

.detail-grid dd {
  margin: 4px 0 0;
  color: var(--text-secondary);
}

.action-section {
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid rgba(33, 44, 66, 0.08);
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.action-section h5 {
  width: 100%;
  margin: 0;
}

.hint-text {
  color: var(--text-muted);
  font-size: 12px;
}

.empty-text {
  margin: 0;
  color: var(--text-muted);
}

label {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 180px;
  color: var(--text-secondary);
  font-size: 13px;
}

input,
select {
  padding: 11px 12px;
  border-radius: 14px;
  border: 1px solid rgba(33, 44, 66, 0.12);
  background: rgba(255, 255, 255, 0.9);
}

.eyebrow {
  font-size: 11px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--text-muted);
}

h3 {
  margin-top: 10px;
  font-family: Georgia, 'Times New Roman', serif;
  font-size: 30px;
}

p {
  margin-top: 10px;
  color: var(--text-secondary);
  line-height: 1.7;
}

.mono {
  font-family: 'Consolas', 'Courier New', monospace;
}

.ghost-btn {
  padding: 12px 16px;
  border-radius: 999px;
  border: 1px solid rgba(16, 98, 89, 0.16);
  background: rgba(255, 255, 255, 0.82);
  font-weight: 600;
}

.error-text {
  margin-bottom: 14px;
  color: #b42318;
}

@media (max-width: 980px) {
  .hero-card,
  .filters-card {
    flex-direction: column;
    align-items: stretch;
  }

  .workspace-grid {
    grid-template-columns: 1fr;
  }

  .detail-grid {
    grid-template-columns: 1fr;
  }
}
</style>
