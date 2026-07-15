<template>
  <section class="settings-shell">
    <article class="hero-card">
      <div>
        <p class="eyebrow">设置</p>
        <h3>前台只读设置摘要</h3>
        <p>运行参数、权限模型和发布策略已经迁移到后台。当前页面只展示只读信息，帮助你理解系统状态与访问边界。</p>
      </div>
      <button class="ghost-btn" @click="loadSummary" :disabled="loading">
        {{ loading ? '刷新中...' : '刷新摘要' }}
      </button>
    </article>

    <p v-if="errorMessage" class="notice error">{{ errorMessage }}</p>
    <p class="readonly-notice">{{ settingsPolicy.readonly_notice }}</p>

    <div class="summary-grid">
      <article v-if="settingsPolicy.show_summary" class="panel">
        <header>
          <p class="label">账号状态</p>
          <h4>{{ currentUser?.username || '未登录' }}</h4>
        </header>
        <div class="kv-list">
          <div class="kv-row">
            <span>角色</span>
            <strong>{{ roleLabel }}</strong>
          </div>
          <div class="kv-row">
            <span>状态</span>
            <strong>{{ currentUser?.status || '未知' }}</strong>
          </div>
          <div class="kv-row">
            <span>后端健康</span>
            <strong>{{ backendHealth }}</strong>
          </div>
          <div class="kv-row">
            <span>版本</span>
            <strong>{{ backendVersion }}</strong>
          </div>
        </div>
      </article>

      <article v-if="settingsPolicy.show_runtime_overview" class="panel">
        <header>
          <p class="label">运行参数</p>
          <h4>只读查看当前配置</h4>
        </header>
        <div class="kv-list">
          <div v-for="item in runtimeEntries" :key="item.key" class="kv-row">
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
          </div>
        </div>
      </article>

      <article v-if="settingsPolicy.show_permission_notice" class="panel full">
        <header>
          <p class="label">使用说明</p>
          <h4>后台接管的能力</h4>
        </header>
        <ul class="policy-list">
          <li>知识库文件的发布、隐藏和角色可见范围由后台统一维护。</li>
          <li>RAG 运行参数、缓存策略和权限模型只允许后台管理员修改。</li>
          <li>前台保留知识库阅读和设置摘要，避免误操作影响全局系统行为。</li>
        </ul>
      </article>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'

import { authApi, getAuthUser, healthApi, knowledgeBaseApi, updateAuthUser } from '../api/index.js'

const defaultSettingsPolicy = () => ({
  show_summary: true,
  show_runtime_overview: true,
  show_permission_notice: true,
  readonly_notice: '前台仅保留系统摘要，正式配置请在后台维护。'
})

const currentUser = ref(getAuthUser())
const runtimeParams = ref({})
const settingsPolicy = ref(defaultSettingsPolicy())
const backendHealth = ref('unknown')
const backendVersion = ref('N/A')
const loading = ref(false)
const errorMessage = ref('')

const roleLabel = computed(() => {
  const labels = {
    super_admin: '超级管理员',
    admin: '管理员',
    operator: '运营',
    user: '前台用户'
  }
  return labels[currentUser.value?.role] || currentUser.value?.role || '未知'
})

const runtimeEntries = computed(() => {
  const entries = [
    ['chunk_size', '分块大小'],
    ['chunk_overlap', '分块重叠'],
    ['top_k', '召回数量'],
    ['similarity_threshold', '相似度阈值'],
    ['enable_cache', '启用缓存'],
    ['enable_rerank', '启用重排'],
    ['enable_hybrid', '启用混合检索'],
    ['enable_self_rag', '启用 Self-RAG']
  ]
  return entries.map(([key, label]) => ({
    key,
    label,
    value: runtimeParams.value[key] ?? '未配置'
  }))
})

async function loadSummary() {
  loading.value = true
  errorMessage.value = ''

  try {
    const [meResponse, paramsResponse, healthResponse] = await Promise.all([
      authApi.me(),
      knowledgeBaseApi.getParams(),
      healthApi.check()
    ])

    currentUser.value = updateAuthUser(meResponse.data)
    runtimeParams.value = paramsResponse.data.params || {}
    settingsPolicy.value = {
      ...defaultSettingsPolicy(),
      ...((paramsResponse.data.frontend_policy && paramsResponse.data.frontend_policy.settings) || {})
    }
    backendHealth.value = healthResponse.data.status || 'unknown'
    backendVersion.value = healthResponse.data.version || 'N/A'
  } catch (error) {
    errorMessage.value = error.response?.data?.detail || error.message || '加载设置摘要失败'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadSummary()
})
</script>

<style scoped>
.settings-shell {
  display: grid;
  gap: 18px;
}

.hero-card,
.panel {
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

.summary-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
}

.panel {
  padding: 22px;
}

.panel.full {
  grid-column: 1 / -1;
}

.readonly-notice {
  padding: 14px 16px;
  border-radius: 16px;
  background: rgba(246, 241, 233, 0.72);
  color: var(--text-secondary);
}

.eyebrow,
.label {
  font-size: 11px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--text-muted);
}

h3,
h4 {
  margin-top: 10px;
  font-family: Georgia, 'Times New Roman', serif;
}

.kv-list {
  display: grid;
  gap: 12px;
  margin-top: 16px;
}

.kv-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px;
  border-radius: 16px;
  background: rgba(246, 241, 233, 0.72);
}

.policy-list {
  margin-top: 16px;
  padding-left: 18px;
  color: var(--text-secondary);
  line-height: 1.8;
}

.notice.error {
  padding: 14px 16px;
  border-radius: 16px;
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
  .summary-grid {
    grid-template-columns: 1fr;
  }

  .hero-card {
    flex-direction: column;
  }
}
</style>
