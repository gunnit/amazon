import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { User, Organization } from '@/types'
import { authApi } from '@/services/api'

interface AuthState {
  user: User | null
  organization: Organization | null
  isAuthenticated: boolean
  isLoading: boolean
  error: string | null

  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string, fullName?: string) => Promise<void>
  logout: () => void
  loadUser: () => Promise<void>
  setUser: (user: User) => void
  clearError: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      organization: null,
      isAuthenticated: false,
      isLoading: false,
      error: null,

      login: async (email: string, password: string) => {
        set({ isLoading: true, error: null })
        try {
          const tokens = await authApi.login(email, password)
          localStorage.setItem('access_token', tokens.access_token)
          localStorage.setItem('refresh_token', tokens.refresh_token)

          const user = await authApi.getCurrentUser()
          const organization = await authApi.getOrganization()

          set({
            user,
            organization,
            isAuthenticated: true,
            isLoading: false
          })
        } catch (error: unknown) {
          const errorMessage = error instanceof Error
            ? error.message
            : 'Login failed'
          set({
            error: errorMessage,
            isLoading: false
          })
          throw error
        }
      },

      register: async (email: string, password: string, fullName?: string) => {
        set({ isLoading: true, error: null })
        try {
          await authApi.register(email, password, fullName)
          // Auto-login after registration
          await get().login(email, password)
        } catch (error: unknown) {
          const errorMessage = error instanceof Error
            ? error.message
            : 'Registration failed'
          set({
            error: errorMessage,
            isLoading: false
          })
          throw error
        }
      },

      logout: () => {
        localStorage.removeItem('access_token')
        localStorage.removeItem('refresh_token')
        set({
          user: null,
          organization: null,
          isAuthenticated: false
        })
      },

      loadUser: async () => {
        const token = localStorage.getItem('access_token')
        if (!token) {
          set({ isAuthenticated: false })
          return
        }

        set({ isLoading: true })
        try {
          const user = await authApi.getCurrentUser()
          const organization = await authApi.getOrganization()
          set({
            user,
            organization,
            isAuthenticated: true,
            isLoading: false
          })
        } catch {
          localStorage.removeItem('access_token')
          localStorage.removeItem('refresh_token')
          set({
            user: null,
            organization: null,
            isAuthenticated: false,
            isLoading: false
          })
        }
      },

      setUser: (user: User) => set({ user }),

      clearError: () => set({ error: null }),
    }),
    {
      name: 'auth-storage',
      partialize: (state) => ({
        isAuthenticated: state.isAuthenticated,
        user: state.user,
        organization: state.organization,
      }),
    }
  )
)
