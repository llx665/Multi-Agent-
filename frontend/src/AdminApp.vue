<template>
  <div class="admin-root">
    <div v-if="loading" class="admin-state-card">
      <p class="eyebrow">后台初始化</p>
      <h1>正在校验后台会话</h1>
      <p>正在读取账号状态与角色权限，请稍候。</p>
    </div>

    <AuthPanel v-else-if="!currentUser" @authenticated="hydrateCurrentUser" />

    <section v-else-if="!hasAccess" class="denied-shell">
      <div class="admin-state-card denied">
        <p class="eyebrow">访问受限</p>
        <h1>无后台访问权限</h1>
        <p>当前账号可以查看前台内容，但没有进入后台管理模块的角色权限。</p>
        <div class="state-actions">
          <button class="ghost-btn" @click="handleSignOut">退出后台</button>
        </div>
      </div>
    </section>

    <AdminLayout v-else :current-user="currentUser" @sign-out="handleSignOut">
      <RouterView />
    </AdminLayout>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'

import AuthPanel from './components/AuthPanel.vue'
import AdminLayout from './admin/layouts/AdminLayout.vue'
import { authApi } from './api/index.js'
import { clearAuthSession, getAuthUser, updateAuthUser } from './auth/session.js'

const allowedRoles = new Set(['operator', 'admin', 'super_admin'])
const currentUser = ref(null)
const loading = ref(true)

const hasAccess = computed(() => allowedRoles.has(currentUser.value?.role || ''))

async function hydrateCurrentUser() {
  const cachedUser = getAuthUser()
  if (!cachedUser?.user_id) {
    currentUser.value = null
    loading.value = false
    return
  }

  loading.value = true
  try {
    const response = await authApi.me()
    currentUser.value = updateAuthUser(response.data)
  } catch {
    clearAuthSession()
    currentUser.value = null
  } finally {
    loading.value = false
  }
}

function handleSignOut() {
  clearAuthSession()
  currentUser.value = null
}

onMounted(() => {
  hydrateCurrentUser()
})
</script>

<style scoped>
.admin-root {
  min-height: 100vh;
}

.denied-shell,
.admin-state-card {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 28px;
}

.admin-state-card {
  max-width: 560px;
  margin: 0 auto;
  background: rgba(255, 250, 242, 0.88);
  border: 1px solid rgba(34, 48, 70, 0.08);
  border-radius: 28px;
  box-shadow: 0 24px 60px rgba(33, 44, 66, 0.12);
  text-align: left;
}

.admin-state-card > * + * {
  margin-top: 12px;
}

.denied {
  background: linear-gradient(180deg, rgba(255, 249, 244, 0.96), rgba(248, 238, 230, 0.92));
}

.eyebrow {
  font-size: 12px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--text-muted);
}

h1 {
  font-family: Georgia, 'Times New Roman', serif;
  font-size: clamp(30px, 4vw, 42px);
  color: var(--text-primary);
}

p {
  color: var(--text-secondary);
  line-height: 1.7;
}

.state-actions {
  display: flex;
  gap: 12px;
  margin-top: 20px;
}

.ghost-btn {
  padding: 12px 18px;
  border-radius: 999px;
  border: 1px solid rgba(16, 98, 89, 0.18);
  background: rgba(255, 255, 255, 0.72);
  color: var(--text-primary);
  font-weight: 600;
}
</style>
