<template>
  <section class="page-grid dashboard-page">
    <article class="hero-card">
      <p class="eyebrow">后台总览</p>
      <h3>统一工作台已接入后台权限底座</h3>
      <p>当前阶段已经具备统一登录校验、角色导航、管理路由守卫和基础审计日志能力。</p>
    </article>

    <article class="status-card">
      <span class="label">当前角色</span>
      <strong>{{ currentUser.role || '未知' }}</strong>
      <span class="muted">可以进入的模块会随角色自动过滤。</span>
    </article>

    <article class="status-card wide">
      <span class="label">可用模块</span>
      <div class="module-list">
        <span v-for="item in availableModules" :key="item.key">{{ item.label }}</span>
      </div>
    </article>

    <article class="status-card wide">
      <div class="card-head">
        <div>
          <span class="label">服务摘要</span>
          <strong>{{ summary.current_user?.role ? '后台接口可用' : '正在加载' }}</strong>
        </div>
        <button class="ghost-btn" @click="loadSummary" :disabled="loading">{{ loading ? '刷新中…' : '刷新摘要' }}</button>
      </div>
      <p class="muted" v-if="errorMessage">{{ errorMessage }}</p>
      <p class="muted" v-else>已接入模块：{{ (summary.modules || []).join('、') || '无' }}</p>
    </article>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'

import { dashboardAdminApi } from '../../admin-api.js'
import { getAuthUser } from '../../auth/session.js'
import { buildAdminNav } from '../nav.js'

const summary = ref({})
const loading = ref(false)
const errorMessage = ref('')
const currentUser = getAuthUser() || {}
const availableModules = computed(() => buildAdminNav(currentUser.role))

async function loadSummary() {
  loading.value = true
  errorMessage.value = ''
  try {
    const response = await dashboardAdminApi.getSummary()
    summary.value = response.data || {}
  } catch (error) {
    errorMessage.value = error.response?.data?.detail || error.message || '加载后台摘要失败'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadSummary()
})
</script>

<style scoped>
.page-grid {
  display: grid;
  grid-template-columns: repeat(12, minmax(0, 1fr));
  gap: 18px;
}

.hero-card,
.status-card {
  padding: 24px;
  border-radius: 26px;
  background: rgba(255, 252, 247, 0.84);
  border: 1px solid rgba(33, 44, 66, 0.08);
  box-shadow: 0 16px 40px rgba(33, 44, 66, 0.08);
}

.hero-card {
  grid-column: span 8;
  background: linear-gradient(135deg, rgba(17, 117, 104, 0.94), rgba(18, 58, 71, 0.94));
  color: #f8f4ef;
}

.hero-card p,
.hero-card .eyebrow {
  color: rgba(248, 244, 239, 0.78);
}

.status-card {
  grid-column: span 4;
}

.status-card.wide {
  grid-column: span 6;
}

.eyebrow,
.label {
  font-size: 11px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}

h3,
strong {
  display: block;
  margin-top: 10px;
}

h3 {
  font-family: Georgia, 'Times New Roman', serif;
  font-size: clamp(28px, 3vw, 38px);
}

p,
.muted {
  margin-top: 10px;
  color: var(--text-secondary);
  line-height: 1.7;
}

.module-list {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 14px;
}

.module-list span {
  padding: 8px 12px;
  border-radius: 999px;
  background: rgba(16, 98, 89, 0.1);
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 600;
}

.card-head {
  display: flex;
  justify-content: space-between;
  gap: 14px;
}

.ghost-btn {
  border-radius: 999px;
  padding: 12px 16px;
  border: 1px solid rgba(16, 98, 89, 0.16);
  background: rgba(255, 255, 255, 0.82);
  font-weight: 600;
}

@media (max-width: 900px) {
  .hero-card,
  .status-card,
  .status-card.wide {
    grid-column: 1 / -1;
  }

  .card-head {
    flex-direction: column;
  }
}
</style>
