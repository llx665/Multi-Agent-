<template>
  <AuthPanel v-if="!authUser" @authenticated="onAuthenticated" />

  <div v-else class="app-container">
    <header class="app-header">
      <div class="header-brand">
        <svg class="brand-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
        </svg>
        <h1>智能客服系统</h1>
      </div>

      <nav class="tabs">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          :class="{ active: activeTab === tab.key }"
          @click="activeTab = tab.key"
        >
          <span class="tab-icon" v-html="tab.icon"></span>
          {{ tab.label }}
        </button>
      </nav>

      <div class="user-box">
        <span class="user-name">{{ authUser.username }}</span>
        <button class="logout-btn" @click="logout">退出</button>
      </div>
    </header>

    <main class="app-main">
      <ChatPanel v-show="activeTab === 'chat'" />
      <KnowledgeBasePanel v-show="activeTab === 'knowledge'" />
      <SettingsPanel v-show="activeTab === 'settings'" />
    </main>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import AuthPanel from './components/AuthPanel.vue'
import ChatPanel from './components/ChatPanel.vue'
import KnowledgeBasePanel from './components/KnowledgeBasePanel.vue'
import SettingsPanel from './components/SettingsPanel.vue'
import { authApi, clearAuthSession, getAuthUser } from './api/index.js'

const activeTab = ref('chat')
const authUser = ref(getAuthUser())

const tabs = [
  {
    key: 'chat',
    label: '对话',
    icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>'
  },
  {
    key: 'knowledge',
    label: '知识库',
    icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>'
  },
  {
    key: 'settings',
    label: '设置',
    icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M12 1v4m0 14v4m-7.07-2.93l2.83-2.83m8.48-8.48l2.83-2.83M1 12h4m14 0h4m-2.93 7.07l-2.83-2.83M6.34 6.34L3.51 3.51"/></svg>'
  }
]

function onAuthenticated(user) {
  authUser.value = user
}

function logout() {
  clearAuthSession()
  authUser.value = null
  activeTab.value = 'chat'
}

onMounted(async () => {
  if (!authUser.value) return
  try {
    const res = await authApi.me()
    authUser.value = {
      user_id: res.data.user_id,
      username: res.data.username,
      role: res.data.role,
      status: res.data.status,
      expires_at: res.data.expires_at,
    }
  } catch {
    clearAuthSession()
    authUser.value = null
  }
})
</script>

<style scoped>
.app-container {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  background: var(--bg);
}

.app-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  height: 56px;
  padding: 0 24px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 0;
  z-index: 100;
  gap: 16px;
}

.header-brand {
  display: flex;
  align-items: center;
  gap: 10px;
}

.brand-icon {
  width: 22px;
  height: 22px;
  color: var(--accent);
}

.header-brand h1 {
  margin: 0;
  font-size: 17px;
  font-weight: 600;
  color: var(--text-primary);
}

.tabs {
  display: flex;
  gap: 4px;
}

.tabs button {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 16px;
  border: none;
  background: transparent;
  border-radius: 8px;
  font-size: 14px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--transition);
  position: relative;
}

.tabs button:hover {
  color: var(--text-primary);
  background: var(--border-light);
}

.tabs button.active {
  color: var(--accent);
  background: var(--accent-light);
  font-weight: 500;
}

.tabs button.active::after {
  content: '';
  position: absolute;
  bottom: -1px;
  left: 50%;
  transform: translateX(-50%);
  width: 20px;
  height: 2px;
  background: var(--accent);
  border-radius: 1px;
}

.tab-icon {
  display: flex;
  width: 16px;
  height: 16px;
}

.tab-icon :deep(svg) {
  width: 100%;
  height: 100%;
}

.user-box {
  display: flex;
  align-items: center;
  gap: 8px;
}

.user-name {
  font-size: 13px;
  color: var(--text-secondary);
}

.logout-btn {
  border: 1px solid var(--border);
  background: transparent;
  border-radius: 8px;
  padding: 6px 10px;
  font-size: 12px;
}

.logout-btn:hover {
  border-color: var(--error);
  color: var(--error);
}

.app-main {
  flex: 1;
  padding: 24px;
  max-width: 1400px;
  width: 100%;
  margin: 0 auto;
}
</style>
