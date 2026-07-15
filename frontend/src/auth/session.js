const TOKEN_KEY = 'auth_token'
const USER_KEY = 'auth_user'

export function getAuthToken() {
  return localStorage.getItem(TOKEN_KEY) || ''
}

export function getAuthUser() {
  try {
    const raw = localStorage.getItem(USER_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export function setAuthSession(session) {
  const currentUser = getAuthUser() || {}
  if (session?.token) {
    localStorage.setItem(TOKEN_KEY, session.token)
  }

  const nextUser = {
    ...currentUser,
    user_id: session?.user_id ?? currentUser.user_id ?? '',
    username: session?.username ?? currentUser.username ?? '',
    role: session?.role ?? currentUser.role ?? '',
    status: session?.status ?? currentUser.status ?? '',
    expires_at: session?.expires_at ?? currentUser.expires_at ?? null
  }

  localStorage.setItem(USER_KEY, JSON.stringify(nextUser))
  return nextUser
}

export function updateAuthUser(user) {
  return setAuthSession(user)
}

export function clearAuthSession() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}
