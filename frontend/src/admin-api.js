import axios from 'axios'
import { getAuthToken } from './auth/session.js'

const adminApi = axios.create({
  baseURL: '/api/admin',
  timeout: 60000,
  headers: {
    'Content-Type': 'application/json'
  }
})

adminApi.interceptors.request.use((config) => {
  const token = getAuthToken()
  if (token) {
    config.headers = config.headers || {}
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

export const dashboardAdminApi = {
  getSummary() {
    return adminApi.get('/dashboard/summary')
  }
}

export const memoryAdminApi = {
  listUsers(params = {}) {
    return adminApi.get('/memory/users', { params })
  },

  getUser(userId) {
    return adminApi.get(`/memory/users/${encodeURIComponent(userId)}`)
  },

  updatePreference(userId, payload) {
    return adminApi.post(`/memory/users/${encodeURIComponent(userId)}/preferences`, payload)
  },

  clearContext(userId) {
    return adminApi.delete(`/memory/users/${encodeURIComponent(userId)}/context`)
  },

  clearAll(userId) {
    return adminApi.delete(`/memory/users/${encodeURIComponent(userId)}`)
  }
}

export const userAdminApi = {
  listUsers(params = {}) {
    return adminApi.get('/users', { params })
  },

  getUser(userId) {
    return adminApi.get(`/users/${encodeURIComponent(userId)}`)
  },

  updateStatus(userId, status) {
    return adminApi.patch(`/users/${encodeURIComponent(userId)}/status`, { status })
  },

  updateRole(userId, role) {
    return adminApi.patch(`/users/${encodeURIComponent(userId)}/role`, { role })
  }
}

export const knowledgeAdminApi = {
  listDocuments(params = {}) {
    return adminApi.get('/knowledge/documents', { params })
  },

  getDocument(documentId) {
    return adminApi.get(`/knowledge/documents/${encodeURIComponent(documentId)}`)
  },

  listDocumentVersions(documentId) {
    return adminApi.get(`/knowledge/documents/${encodeURIComponent(documentId)}/versions`)
  },

  getDocumentVersion(documentId, versionId) {
    return adminApi.get(
      `/knowledge/documents/${encodeURIComponent(documentId)}/versions/${encodeURIComponent(versionId)}`
    )
  },

  createDocument(payload) {
    const formData = new FormData()
    formData.append('file', payload.file)
    formData.append('description', payload.description || '')
    formData.append('tags', JSON.stringify(payload.tags || []))
    formData.append('allowed_roles', JSON.stringify(payload.allowed_roles || []))
    formData.append('published', JSON.stringify(Boolean(payload.published)))
    formData.append('visible_to_frontend', JSON.stringify(Boolean(payload.visible_to_frontend)))
    return adminApi.post('/knowledge/documents', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
  },

  updateDocument(documentId, payload) {
    return adminApi.patch(`/knowledge/documents/${encodeURIComponent(documentId)}`, payload)
  },

  replaceDocument(documentId, file) {
    const formData = new FormData()
    formData.append('file', file)
    return adminApi.post(`/knowledge/documents/${encodeURIComponent(documentId)}/replace`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
  },

  deleteDocument(documentId) {
    return adminApi.delete(`/knowledge/documents/${encodeURIComponent(documentId)}`)
  },

  restoreDocument(documentId) {
    return adminApi.post(`/knowledge/documents/${encodeURIComponent(documentId)}/restore`)
  },

  rollbackDocument(documentId, payload) {
    return adminApi.post(`/knowledge/documents/${encodeURIComponent(documentId)}/rollback`, payload)
  }
}

export const settingsAdminApi = {
  getSummary() {
    return adminApi.get('/settings/summary')
  },

  updateRuntime(payload) {
    return adminApi.post('/settings/runtime', payload)
  },

  updateFrontendPolicy(payload) {
    return adminApi.post('/settings/frontend-policy', payload)
  }
}

export default adminApi
