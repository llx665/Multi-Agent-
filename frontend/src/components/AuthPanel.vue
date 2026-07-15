<template>
  <div class="auth-wrap">
    <div class="auth-card">
      <h2>登录 / 注册</h2>
      <p class="hint">登录后，记忆将与账号绑定并跨会话持久化。</p>

      <div class="tabs">
        <button :class="{ active: mode === 'login' }" @click="mode = 'login'">登录</button>
        <button :class="{ active: mode === 'register' }" @click="mode = 'register'">注册</button>
      </div>

      <div class="form">
        <label>
          用户名
          <input v-model.trim="username" placeholder="3-64位，支持字母数字._-@" />
        </label>
        <label>
          密码
          <input v-model="password" type="password" placeholder="至少8位" />
        </label>
        <button class="submit" :disabled="loading" @click="submitAuth">
          {{ loading ? '提交中...' : mode === 'login' ? '登录' : '注册并登录' }}
        </button>
        <p v-if="error" class="error">{{ error }}</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { authApi, setAuthSession } from '../api/index.js'

const emit = defineEmits(['authenticated'])

const mode = ref('login')
const username = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')

async function submitAuth() {
  if (!username.value || !password.value) {
    error.value = '请输入用户名和密码'
    return
  }

  loading.value = true
  error.value = ''

  try {
    const res = mode.value === 'login'
      ? await authApi.login(username.value, password.value)
      : await authApi.register(username.value, password.value)

    const session = res.data
    setAuthSession(session)
    emit('authenticated', {
      user_id: session.user_id,
      username: session.username,
      expires_at: session.expires_at,
    })
  } catch (e) {
    error.value = e.response?.data?.detail || e.message || '认证失败'
  }

  loading.value = false
}
</script>

<style scoped>
.auth-wrap {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
}

.auth-card {
  width: 100%;
  max-width: 420px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 20px;
  box-shadow: var(--shadow-md);
}

.auth-card h2 {
  margin: 0 0 6px;
}

.hint {
  margin: 0 0 14px;
  color: var(--text-secondary);
  font-size: 13px;
}

.tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 14px;
}

.tabs button {
  flex: 1;
  border: 1px solid var(--border);
  background: transparent;
  border-radius: 8px;
  padding: 8px 10px;
}

.tabs button.active {
  border-color: var(--accent);
  background: var(--accent-light);
  color: var(--accent);
}

.form {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 13px;
}

input {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 9px 10px;
}

.submit {
  border: none;
  background: var(--accent);
  color: #fff;
  border-radius: 8px;
  padding: 10px;
}

.submit:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.error {
  color: var(--error);
  font-size: 13px;
  margin: 0;
}
</style>
