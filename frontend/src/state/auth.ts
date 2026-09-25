import { create } from 'zustand'
import { authApi, type AuthUser } from '../api/endpoints'

export type AuthStatus = 'checking' | 'authed' | 'anon'

interface AuthState {
  status: AuthStatus
  user: AuthUser | null
}

export const useAuth = create<AuthState>()(() => ({ status: 'checking', user: null }))

export async function checkAuth(): Promise<void> {
  try {
    const { user } = await authApi.me()
    useAuth.setState({ status: 'authed', user })
  } catch {
    useAuth.setState({ status: 'anon', user: null })
  }
}

export function markSignedOut(): void {
  useAuth.setState({ status: 'anon', user: null })
}

if (typeof window !== 'undefined') {
  window.addEventListener('vibrato:unauthorized', markSignedOut)
}

export async function signOut(): Promise<void> {
  try {
    await authApi.logout()
  } finally {
    markSignedOut()
  }
}
