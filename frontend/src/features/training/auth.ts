export type AuthUser = { id: number; username: string; role: 'viewer' | 'scheduler' | 'approver' }
export type AuthState = { token: string; user: AuthUser }

const TOKEN_KEY = 'project-ai-tf.access-token'
const USER_KEY = 'project-ai-tf.auth-user'

export function readAuth(): AuthState | null {
  const token = window.localStorage.getItem(TOKEN_KEY)
  const encodedUser = window.localStorage.getItem(USER_KEY)
  if (!token || !encodedUser) return null
  try {
    return { token, user: JSON.parse(encodedUser) as AuthUser }
  } catch {
    clearAuth()
    return null
  }
}

export function storeAuth(state: AuthState): void {
  window.localStorage.setItem(TOKEN_KEY, state.token)
  window.localStorage.setItem(USER_KEY, JSON.stringify(state.user))
  window.dispatchEvent(new Event('training-auth-change'))
}

export function clearAuth(): void {
  window.localStorage.removeItem(TOKEN_KEY)
  window.localStorage.removeItem(USER_KEY)
  window.dispatchEvent(new Event('training-auth-change'))
}

export async function authenticatedFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers)
  const token = readAuth()?.token
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const response = await fetch(input, { ...init, headers })
  if (response.status === 401 && token) clearAuth()
  return response
}

export function apiBase(): string {
  return import.meta.env.VITE_API_BASE_URL ?? '/api'
}