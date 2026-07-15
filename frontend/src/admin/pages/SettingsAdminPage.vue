<template>
  <section class="settings-admin-page">
    <article class="hero-card">
      <div>
        <p class="eyebrow">系统设置</p>
        <h3>统一维护运行参数、前台策略与权限说明</h3>
        <p>这里集中承接原前台设置能力。管理员可以分别维护运行参数和前台展示策略，不同区域独立保存、独立报错。</p>
      </div>
      <button class="ghost-btn" @click="loadSummary" :disabled="loading">
        {{ loading ? '刷新中...' : '刷新设置摘要' }}
      </button>
    </article>

    <div class="settings-grid">
      <article class="panel">
        <header class="panel-head">
          <div>
            <p class="label">运行参数</p>
            <h4>后台可编辑配置</h4>
          </div>
          <button
            class="solid-btn"
            data-testid="save-runtime-btn"
            @click="saveRuntime"
            :disabled="savingRuntime"
          >
            {{ savingRuntime ? '保存中...' : '保存运行参数' }}
          </button>
        </header>

        <p v-if="runtimeSuccessMessage" class="notice success" data-testid="runtime-success">
          {{ runtimeSuccessMessage }}
        </p>
        <p v-if="runtimeErrorMessage" class="notice error" data-testid="runtime-error">
          {{ runtimeErrorMessage }}
        </p>

        <form class="form-grid" data-testid="runtime-form" @submit.prevent="saveRuntime">
          <label>
            分块大小
            <input
              data-testid="runtime-chunk-size"
              v-model.number="runtimeParams.chunk_size"
              type="number"
              min="100"
              max="1200"
              step="50"
            />
          </label>
          <label>
            分块重叠
            <input
              data-testid="runtime-chunk-overlap"
              v-model.number="runtimeParams.chunk_overlap"
              type="number"
              min="0"
              max="400"
              step="10"
            />
          </label>
          <label>
            召回数量
            <input data-testid="runtime-top-k" v-model.number="runtimeParams.top_k" type="number" min="1" max="20" />
          </label>
          <label>
            相似度阈值
            <input
              v-model.number="runtimeParams.similarity_threshold"
              type="number"
              min="0"
              max="1"
              step="0.05"
            />
          </label>
        </form>

        <div class="switch-grid">
          <label class="switch-item">
            <span>启用缓存</span>
            <input v-model="runtimeParams.enable_cache" type="checkbox" />
          </label>
          <label class="switch-item">
            <span>启用重排</span>
            <input v-model="runtimeParams.enable_rerank" type="checkbox" />
          </label>
          <label class="switch-item">
            <span>启用混合检索</span>
            <input v-model="runtimeParams.enable_hybrid" type="checkbox" />
          </label>
          <label class="switch-item">
            <span>启用 Self-RAG</span>
            <input v-model="runtimeParams.enable_self_rag" type="checkbox" />
          </label>
        </div>
      </article>

      <article class="panel">
        <header class="panel-head">
          <div>
            <p class="label">前台展示策略</p>
            <h4>知识库与摘要页可见性</h4>
          </div>
          <button
            class="solid-btn"
            data-testid="save-frontend-policy-btn"
            @click="saveFrontendPolicy"
            :disabled="savingFrontendPolicy"
          >
            {{ savingFrontendPolicy ? '保存中...' : '保存前台策略' }}
          </button>
        </header>

        <p v-if="frontendPolicySuccessMessage" class="notice success" data-testid="frontend-policy-success">
          {{ frontendPolicySuccessMessage }}
        </p>
        <p v-if="frontendPolicyErrorMessage" class="notice error" data-testid="frontend-policy-error">
          {{ frontendPolicyErrorMessage }}
        </p>

        <form class="form-grid" data-testid="frontend-policy-form" @submit.prevent="saveFrontendPolicy">
          <label class="full-width">
            知识库介绍文案
            <textarea data-testid="policy-intro-text" v-model="frontendPolicy.knowledge_base.intro_text" rows="3" />
          </label>
          <label class="full-width">
            知识库空状态文案
            <textarea
              data-testid="policy-empty-state-text"
              v-model="frontendPolicy.knowledge_base.empty_state_text"
              rows="3"
            />
          </label>
          <label class="full-width">
            知识库只读提示
            <textarea v-model="frontendPolicy.knowledge_base.readonly_notice" rows="3" />
          </label>
          <label class="full-width">
            设置页只读提示
            <textarea v-model="frontendPolicy.settings.readonly_notice" rows="3" />
          </label>
        </form>

        <div class="switch-grid">
          <label class="switch-item">
            <span>显示知识库文档指标</span>
            <input
              data-testid="policy-show-document-metrics"
              v-model="frontendPolicy.knowledge_base.show_document_metrics"
              type="checkbox"
            />
          </label>
          <label class="switch-item">
            <span>显示摘要卡片</span>
            <input v-model="frontendPolicy.settings.show_summary" type="checkbox" />
          </label>
          <label class="switch-item">
            <span>显示运行参数概览</span>
            <input
              data-testid="policy-show-runtime-overview"
              v-model="frontendPolicy.settings.show_runtime_overview"
              type="checkbox"
            />
          </label>
          <label class="switch-item">
            <span>显示权限说明</span>
            <input v-model="frontendPolicy.settings.show_permission_notice" type="checkbox" />
          </label>
        </div>
      </article>

      <article class="panel full">
        <header class="panel-head">
          <div>
            <p class="label">权限模型</p>
            <h4>角色职责边界</h4>
          </div>
        </header>

        <div class="role-grid">
          <div v-for="(role, key) in permissionRoles" :key="key" class="role-card">
            <strong>{{ role.label }}</strong>
            <p class="role-key">{{ key }}</p>
            <ul>
              <li v-for="item in role.capabilities" :key="item">{{ item }}</li>
            </ul>
          </div>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'

import { settingsAdminApi } from '../../admin-api.js'

const defaultRuntimeParams = () => ({
  chunk_size: 400,
  chunk_overlap: 50,
  top_k: 5,
  similarity_threshold: 0.3,
  enable_cache: true,
  enable_rerank: true,
  enable_hybrid: true,
  enable_self_rag: false
})

const defaultFrontendPolicy = () => ({
  knowledge_base: {
    intro_text: '',
    empty_state_text: '',
    readonly_notice: '',
    show_document_metrics: true
  },
  settings: {
    show_summary: true,
    show_runtime_overview: true,
    show_permission_notice: true,
    readonly_notice: ''
  }
})

const loading = ref(false)
const savingRuntime = ref(false)
const savingFrontendPolicy = ref(false)
const runtimeParams = ref(defaultRuntimeParams())
const permissionModel = ref({ roles: {} })
const frontendPolicy = ref(defaultFrontendPolicy())
const runtimeErrorMessage = ref('')
const frontendPolicyErrorMessage = ref('')
const runtimeSuccessMessage = ref('')
const frontendPolicySuccessMessage = ref('')

const permissionRoles = computed(() => permissionModel.value.roles || {})

function applySummary(payload) {
  runtimeParams.value = {
    ...defaultRuntimeParams(),
    ...(payload.runtime_params || {})
  }
  permissionModel.value = payload.permission_model || { roles: {} }
  frontendPolicy.value = {
    ...defaultFrontendPolicy(),
    ...(payload.frontend_policy || {}),
    knowledge_base: {
      ...defaultFrontendPolicy().knowledge_base,
      ...((payload.frontend_policy && payload.frontend_policy.knowledge_base) || {})
    },
    settings: {
      ...defaultFrontendPolicy().settings,
      ...((payload.frontend_policy && payload.frontend_policy.settings) || {})
    }
  }
}

async function loadSummary() {
  loading.value = true
  runtimeErrorMessage.value = ''
  frontendPolicyErrorMessage.value = ''
  try {
    const response = await settingsAdminApi.getSummary()
    applySummary(response.data || {})
  } catch (error) {
    runtimeErrorMessage.value = error.response?.data?.detail || error.message || '加载系统设置失败'
  } finally {
    loading.value = false
  }
}

async function saveRuntime() {
  savingRuntime.value = true
  runtimeErrorMessage.value = ''
  runtimeSuccessMessage.value = ''
  try {
    const response = await settingsAdminApi.updateRuntime(runtimeParams.value)
    runtimeParams.value = {
      ...defaultRuntimeParams(),
      ...(response.data.params || {})
    }
    runtimeSuccessMessage.value = '运行参数已保存'
  } catch (error) {
    runtimeErrorMessage.value = error.response?.data?.detail || error.message || '保存运行参数失败'
  } finally {
    savingRuntime.value = false
  }
}

async function saveFrontendPolicy() {
  savingFrontendPolicy.value = true
  frontendPolicyErrorMessage.value = ''
  frontendPolicySuccessMessage.value = ''
  try {
    const response = await settingsAdminApi.updateFrontendPolicy(frontendPolicy.value)
    frontendPolicy.value = {
      ...defaultFrontendPolicy(),
      ...(response.data.policy || {}),
      knowledge_base: {
        ...defaultFrontendPolicy().knowledge_base,
        ...((response.data.policy && response.data.policy.knowledge_base) || {})
      },
      settings: {
        ...defaultFrontendPolicy().settings,
        ...((response.data.policy && response.data.policy.settings) || {})
      }
    }
    frontendPolicySuccessMessage.value = '前台展示策略已保存'
  } catch (error) {
    frontendPolicyErrorMessage.value = error.response?.data?.detail || error.message || '保存前台展示策略失败'
  } finally {
    savingFrontendPolicy.value = false
  }
}

onMounted(() => {
  loadSummary()
})
</script>

<style scoped>
.settings-admin-page {
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

.settings-grid {
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

.panel-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.eyebrow,
.label,
.role-key {
  font-size: 11px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--text-muted);
}

.hero-card h3,
.panel h4,
.role-card strong {
  font-family: Georgia, 'Times New Roman', serif;
}

.form-grid,
.switch-grid,
.role-grid {
  display: grid;
  gap: 14px;
  margin-top: 18px;
}

.form-grid,
.role-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.switch-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.full-width {
  grid-column: 1 / -1;
}

label,
.role-card {
  padding: 16px;
  border-radius: 18px;
  background: rgba(246, 241, 233, 0.72);
}

label {
  display: grid;
  gap: 10px;
  color: var(--text-secondary);
}

input[type='number'],
textarea {
  width: 100%;
  padding: 12px 14px;
  border-radius: 14px;
  border: 1px solid rgba(33, 44, 66, 0.12);
  background: rgba(255, 255, 255, 0.9);
  resize: vertical;
}

.switch-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.role-card ul {
  margin-top: 12px;
  padding-left: 18px;
  color: var(--text-secondary);
  line-height: 1.8;
}

.solid-btn,
.ghost-btn {
  padding: 12px 18px;
  border-radius: 999px;
}

.solid-btn {
  border: none;
  background: var(--accent);
  color: white;
}

.ghost-btn {
  border: 1px solid rgba(16, 98, 89, 0.18);
  background: rgba(255, 255, 255, 0.72);
}

.notice.success,
.notice.error {
  margin-top: 16px;
  padding: 14px 16px;
  border-radius: 16px;
}

.notice.success {
  background: rgba(14, 97, 90, 0.1);
  color: var(--accent);
}

.notice.error {
  background: rgba(180, 71, 55, 0.1);
  color: #9f3427;
}

@media (max-width: 960px) {
  .hero-card,
  .settings-grid,
  .form-grid,
  .switch-grid,
  .role-grid {
    grid-template-columns: 1fr;
  }

  .hero-card {
    flex-direction: column;
  }

  .full-width {
    grid-column: auto;
  }
}
</style>
