<template>
  <div class="chat-panel">
    <div class="messages-container" ref="messagesContainer">
      <div
        v-for="msg in messages"
        :key="msg.id"
        :class="['message', msg.role]"
      >
        <div class="message-bubble" v-html="formatMessage(msg.content)"></div>
        <div class="message-meta">
          <span class="time">{{ formatTime(msg.timestamp) }}</span>
          <span v-if="msg.role === 'assistant' && msg.customerType" class="tag">
            {{ msg.customerType }}
          </span>
        </div>
      </div>

      <div v-if="loading" class="message assistant">
        <div class="message-bubble typing">
          <span class="dot"></span>
          <span class="dot"></span>
          <span class="dot"></span>
        </div>
      </div>
    </div>

    <div class="input-area">
      <div class="input-wrapper">
        <textarea
          v-model="inputMessage"
          @keydown.enter.exact.prevent="sendMessage"
          :disabled="loading"
          rows="1"
          ref="inputTextarea"
          placeholder="输入消息，Enter 发送..."
        ></textarea>
        <button
          class="send-btn"
          @click="sendMessage"
          :disabled="loading || !inputMessage.trim()"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="22" y1="2" x2="11" y2="13"/>
            <polygon points="22 2 15 22 11 13 2 9 22 2"/>
          </svg>
        </button>
      </div>
      <button class="clear-btn" @click="clearHistory" :disabled="loading">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="3 6 5 6 21 6"/>
          <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
        </svg>
        清空会话
      </button>
    </div>
  </div>
</template>

<script setup>
import { nextTick, onMounted, ref } from 'vue'
import { chatApi, getAuthUser } from '../api/index.js'

const messages = ref([])
const inputMessage = ref('')
const loading = ref(false)
const authUser = ref(getAuthUser())
const localUserSeed = ref(getOrCreateLocalUserSeed())
const sessionId = ref('')
const messagesContainer = ref(null)
const inputTextarea = ref(null)

const defaultGreeting = '您好，我是智能客服助手。请告诉我您要咨询的问题。'
const STORAGE_VERSION = 1

onMounted(async () => {
  await restoreConversationState()

  if (inputTextarea.value) {
    inputTextarea.value.focus()
  }
  await nextTick()
  scrollToBottom()
})

function refreshAuthUser() {
  authUser.value = getAuthUser()
  return authUser.value
}

function createSessionId() {
  const current = refreshAuthUser()
  const base = current?.user_id || localUserSeed.value
  return `session_${base}_${createIdSuffix()}`
}

function getOrCreateLocalUserSeed() {
  const storageKey = 'chat_user_seed'
  const cached = localStorage.getItem(storageKey)
  if (cached) return cached

  const generated = `user_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
  localStorage.setItem(storageKey, generated)
  return generated
}

function createIdSuffix() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `${Date.now()}_${Math.random().toString(36).slice(2, 10)}`
}

function createMessage(role, content, extra = {}) {
  return {
    id: `msg_${createIdSuffix()}`,
    role,
    content,
    timestamp: new Date().toISOString(),
    customerType: null,
    ...extra
  }
}

function normalizeMessage(message) {
  if (!message || typeof message !== 'object') return null
  return {
    id: message.id || `msg_${createIdSuffix()}`,
    role: message.role || 'assistant',
    content: message.content || '',
    timestamp: message.timestamp || new Date().toISOString(),
    customerType: message.customerType ?? null
  }
}

function getConversationStorageKey() {
  const current = refreshAuthUser()
  const base = current?.user_id || localUserSeed.value
  return `chat_conversation_v${STORAGE_VERSION}_${base}`
}

function persistConversationState() {
  try {
    localStorage.setItem(getConversationStorageKey(), JSON.stringify({
      sessionId: sessionId.value,
      messages: messages.value
    }))
  } catch (error) {
    console.error('persist conversation failed:', error)
  }
}

async function restoreConversationState() {
  sessionId.value = createSessionId()

  try {
    const raw = localStorage.getItem(getConversationStorageKey())
    if (raw) {
      const stored = JSON.parse(raw)
      if (stored?.sessionId) {
        sessionId.value = stored.sessionId
      }

      if (Array.isArray(stored?.messages) && stored.messages.length > 0) {
        messages.value = stored.messages
          .map(normalizeMessage)
          .filter(Boolean)
        return
      }
    }
  } catch (error) {
    console.error('restore conversation failed:', error)
  }

  const restored = await restoreConversationFromServer()
  if (restored) {
    persistConversationState()
    return
  }

  messages.value = [createMessage('assistant', defaultGreeting)]
  persistConversationState()
}

async function restoreConversationFromServer() {
  try {
    ensureAuthenticated()
  } catch {
    return false
  }

  try {
    const response = await chatApi.getHistory(sessionId.value)
    const history = response.data?.messages || []
    if (!Array.isArray(history) || history.length === 0) {
      return false
    }

    messages.value = history
      .map((msg) => normalizeMessage({
        role: msg.role,
        content: msg.content,
        timestamp: msg.timestamp
      }))
      .filter(Boolean)
    return messages.value.length > 0
  } catch (error) {
    console.error('restore server history failed:', error)
    return false
  }
}

function ensureAuthenticated() {
  const current = refreshAuthUser()
  if (!current || !current.user_id) {
    throw new Error('登录状态已失效，请重新登录。')
  }
  return current
}

async function sendMessage() {
  const trimmed = inputMessage.value.trim()
  if (!trimmed || loading.value) return

  try {
    ensureAuthenticated()
  } catch (authError) {
    messages.value.push(createMessage('assistant', authError.message))
    inputMessage.value = ''
    await nextTick()
    scrollToBottom()
    persistConversationState()
    return
  }

  const userMessage = createMessage('user', trimmed)

  messages.value.push(userMessage)
  inputMessage.value = ''
  loading.value = true

  const history = messages.value.slice(0, -1).map(m => ({
    role: m.role,
    content: m.content
  }))

  const assistantMessage = createMessage('assistant', '')
  messages.value.push(assistantMessage)

  await nextTick()
  scrollToBottom()

  let greetingInserted = false

  try {
    await streamAssistantReply(
      {
        sessionId: sessionId.value,
        message: trimmed,
        history
      },
      assistantMessage,
      (meta) => {
        if (meta.customer_type) {
          assistantMessage.customerType = meta.customer_type
        }

        if (meta.greeting && !greetingInserted) {
          messages.value.splice(messages.value.length - 1, 0, createMessage(
            'assistant',
            meta.greeting,
            { customerType: meta.customer_type || null }
          ))
          greetingInserted = true
        }
      }
    )

    if (!assistantMessage.content.trim()) {
      const response = await chatApi.sendMessage(sessionId.value, trimmed, history)
      assistantMessage.content = response.data.message || ''
      assistantMessage.customerType = response.data.customer_type || null

      if (response.data.greeting && !greetingInserted) {
        messages.value.splice(messages.value.length - 1, 0, createMessage(
          'assistant',
          response.data.greeting,
          { customerType: response.data.customer_type || null }
        ))
      }
    }
  } catch (error) {
    console.error('send message failed:', error)
    assistantMessage.content = `抱歉，发送失败：${error.message || 'unknown error'}`
  }

  loading.value = false
  await nextTick()
  scrollToBottom()
  persistConversationState()
}

async function streamAssistantReply(payload, assistantMessage, onMeta) {
  const response = await chatApi.streamMessage(
    payload.sessionId,
    payload.message,
    payload.history
  )

  if (!response.ok) {
    if (response.status === 401) {
      throw new Error('登录状态已失效，请重新登录。')
    }
    throw new Error(`stream request failed: ${response.status}`)
  }

  if (!response.body) {
    throw new Error('stream body is unavailable')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  while (true) {
    const { value, done } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })

    let splitIndex = buffer.indexOf('\n\n')
    while (splitIndex !== -1) {
      const frame = buffer.slice(0, splitIndex).trim()
      buffer = buffer.slice(splitIndex + 2)

      if (frame) {
        const lines = frame.split('\n')
        for (const line of lines) {
          if (!line.startsWith('data:')) continue
          const data = line.slice(5).trim()
          if (!data) continue

          const chunk = JSON.parse(data)
          if (chunk.error) {
            throw new Error(chunk.error)
          }

          if (typeof chunk.content === 'string' && chunk.content.length > 0) {
            assistantMessage.content += chunk.content
            await nextTick()
            scrollToBottom()
          }

          if (chunk.meta) {
            onMeta(chunk.meta)
          }

          if (chunk.done) {
            return
          }
        }
      }

      splitIndex = buffer.indexOf('\n\n')
    }
  }
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function formatMessage(content) {
  if (!content) return ''

  const safe = escapeHtml(content)
  return safe
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>')
}

function formatTime(timestamp) {
  if (!timestamp) return ''
  const date = new Date(timestamp)
  return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

function scrollToBottom() {
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}

async function clearHistory() {
  if (!confirm('确定要清空当前会话历史吗？')) return

  const previousSessionId = sessionId.value
  try {
    await chatApi.clearHistory(previousSessionId)
  } catch (error) {
    console.error('clear history failed:', error)
  }

  messages.value = [createMessage('assistant', defaultGreeting)]
  sessionId.value = createSessionId()
  persistConversationState()
}
</script>

<style scoped>
.chat-panel {
  height: calc(100vh - 56px - 48px);
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.messages-container {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  border-radius: var(--radius-lg);
  background: var(--surface);
  border: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.message {
  display: flex;
  flex-direction: column;
  max-width: 75%;
}

.message.user {
  align-self: flex-end;
  align-items: flex-end;
}

.message.assistant {
  align-self: flex-start;
  align-items: flex-start;
}

.message-bubble {
  padding: 12px 16px;
  border-radius: 16px;
  line-height: 1.6;
  font-size: 14px;
  word-break: break-word;
}

.message.user .message-bubble {
  background: var(--accent);
  color: #fff;
  border-bottom-right-radius: 4px;
}

.message.assistant .message-bubble {
  background: #F8F9FB;
  border: 1px solid #E8EAED;
  color: var(--text-primary);
  border-bottom-left-radius: 4px;
}

.message.assistant .message-bubble code {
  background: rgba(0, 0, 0, 0.06);
  padding: 2px 6px;
  border-radius: 4px;
  font-family: 'SF Mono', Monaco, monospace;
  font-size: 13px;
}

.message.assistant .message-bubble strong {
  font-weight: 600;
}

.message.typing {
  display: flex;
  gap: 4px;
  padding: 14px 18px;
}

.message.typing .dot {
  width: 8px;
  height: 8px;
  background: var(--text-muted);
  border-radius: 50%;
  animation: bounce 1.4s infinite ease-in-out;
}

.message.typing .dot:nth-child(1) { animation-delay: 0s; }
.message.typing .dot:nth-child(2) { animation-delay: 0.2s; }
.message.typing .dot:nth-child(3) { animation-delay: 0.4s; }

@keyframes bounce {
  0%, 80%, 100% { transform: translateY(0); }
  40% { transform: translateY(-6px); }
}

.message-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
  font-size: 12px;
  color: var(--text-muted);
}

.message.user .message-meta {
  flex-direction: row-reverse;
}

.message-meta .tag {
  background: var(--accent-light);
  color: var(--accent);
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 500;
}

.input-area {
  display: flex;
  align-items: flex-end;
  gap: 12px;
}

.input-wrapper {
  flex: 1;
  display: flex;
  align-items: flex-end;
  gap: 8px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 8px 8px 8px 16px;
  transition: border-color var(--transition), box-shadow var(--transition);
}

.input-wrapper:focus-within {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-light);
}

.input-wrapper textarea {
  flex: 1;
  border: none;
  background: transparent;
  resize: none;
  font-size: 14px;
  line-height: 1.5;
  color: var(--text-primary);
  padding: 4px 0;
  outline: none;
}

.input-wrapper textarea::placeholder {
  color: var(--text-muted);
}

.send-btn {
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 10px;
  background: var(--accent);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all var(--transition);
  flex-shrink: 0;
}

.send-btn:hover:not(:disabled) {
  background: var(--accent-hover);
  transform: scale(1.05);
}

.send-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.send-btn svg {
  width: 18px;
  height: 18px;
}

.clear-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border: 1px solid var(--border);
  background: var(--surface);
  border-radius: var(--radius);
  font-size: 13px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--transition);
}

.clear-btn:hover:not(:disabled) {
  border-color: var(--error);
  color: var(--error);
}

.clear-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.clear-btn svg {
  width: 14px;
  height: 14px;
}
</style>
