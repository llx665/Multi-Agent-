import axios from 'axios'
import {
  clearAuthSession,
  getAuthToken,
  getAuthUser,
  setAuthSession,
  updateAuthUser
} from '../auth/session.js'

const API_BASE = '/api/v1'

const api = axios.create({
  baseURL: API_BASE,
  timeout: 60000,
  headers: {
    'Content-Type': 'application/json'
  }
})

function encodeDocId(docId) {
  return encodeURIComponent(String(docId))
}

api.interceptors.request.use((config) => {
  const token = getAuthToken()
  if (token) {
    config.headers = config.headers || {}
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

export const authApi = {
  register(username, password) {
    return api.post('/auth/register', { username, password })
  },

  login(username, password) {
    return api.post('/auth/login', { username, password })
  },

  me() {
    return api.get('/auth/me')
  },

  getMemoryProfile() {
    return api.get('/auth/memory')
  },

  resolveMemoryPreference(key, value, confidence = 1.0) {
    return api.post('/auth/memory/resolve', { key, value, confidence })
  }
}

export const chatApi = {
  sendMessage(sessionId, message, history = []) {
    const user = getAuthUser()
    return api.post('/chat', {
      session_id: sessionId,
      user_id: user?.user_id || null,
      message,
      history
    })
  },

  streamMessage(sessionId, message, history = []) {
    const token = getAuthToken()
    const user = getAuthUser()

    return fetch(`${API_BASE}/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {})
      },
      body: JSON.stringify({
        session_id: sessionId,
        user_id: user?.user_id || null,
        message,
        history
      })
    })
  },

  getHistory(sessionId) {
    return api.get(`/chat/history/${encodeURIComponent(sessionId)}`)
  },

  clearHistory(sessionId) {
    return api.delete(`/chat/history/${encodeURIComponent(sessionId)}`)
  }
}

export const skillsApi = {
  getSkills() {
    return api.get('/skills')
  },

  getSkill(skillName) {
    return api.get(`/skills/${encodeURIComponent(skillName)}`)
  },

  getStats() {
    return api.get('/skills/stats')
  }
}

export const healthApi = {
  check() {
    return api.get('/health')
  }
}

export const knowledgeBaseApi = {
  getDocuments() {
    return api.get('/knowledge-base')
  },

  getDocument(docId) {
    return api.get(`/knowledge-base/${encodeDocId(docId)}`)
  },

  getParams() {
    return api.get('/knowledge-base/params')
  },

  updateParams(params) {
    return api.post('/knowledge-base/params', params)
  },

  reloadKnowledgeBase() {
    return api.post('/knowledge-base/reload')
  },

  clearCache() {
    return api.post('/knowledge-base/clear-cache')
  }
}

export { clearAuthSession, getAuthToken, getAuthUser, setAuthSession, updateAuthUser }

export default api
