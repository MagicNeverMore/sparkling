import { create } from 'zustand'
import { api } from './api'

export interface AuthUser {
  username: string
  email?: string | null
}

interface AuthStatusRaw {
  initialized: boolean
  authenticated: boolean
  user?: AuthUser | null
}

interface AuthState {
  initialized: boolean
  authenticated: boolean
  user: AuthUser | null
  loading: boolean
  statusLoaded: boolean
  loadStatus: () => Promise<void>
  register: (payload: { username: string; password: string; email?: string }) => Promise<void>
  login: (payload: { username: string; password: string }) => Promise<void>
  logout: () => Promise<void>
  updateMe: (payload: { username?: string; email?: string; password?: string }) => Promise<void>
  markLoggedOut: () => void
}

const applyStatus = (raw: AuthStatusRaw) => ({
  initialized: raw.initialized,
  authenticated: raw.authenticated,
  user: raw.user ?? null,
  statusLoaded: true,
})

export const useAuthStore = create<AuthState>((set) => ({
  initialized: false,
  authenticated: false,
  user: null,
  loading: true,
  statusLoaded: false,

  loadStatus: async () => {
    set({ loading: true })
    try {
      const raw = await api.get<AuthStatusRaw>('/api/auth/status')
      set({ ...applyStatus(raw), loading: false })
    } catch {
      set({ initialized: false, authenticated: false, user: null, statusLoaded: true, loading: false })
    }
  },

  register: async (payload) => {
    const user = await api.post<AuthUser>('/api/auth/register', payload)
    set({ initialized: true, authenticated: true, user })
  },

  login: async (payload) => {
    const user = await api.post<AuthUser>('/api/auth/login', payload)
    set({ initialized: true, authenticated: true, user })
  },

  logout: async () => {
    try {
      await api.post('/api/auth/logout')
    } finally {
      set({ authenticated: false, user: null, initialized: true })
    }
  },

  updateMe: async (payload) => {
    const user = await api.put<AuthUser>('/api/auth/me', payload)
    set({ user, authenticated: true, initialized: true })
  },

  markLoggedOut: () => set({ authenticated: false, user: null }),
}))
