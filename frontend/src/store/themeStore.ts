import { create } from 'zustand'
import { persist } from 'zustand/middleware'

type Theme = 'light' | 'dark' | 'system'

interface ThemeState {
  theme: Theme
  resolvedTheme: 'light' | 'dark'
  setTheme: (theme: Theme) => void
  toggleTheme: () => void
}

const getSystemTheme = (): 'light' | 'dark' => {
  if (typeof window === 'undefined') return 'light'
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

const resolveTheme = (theme: Theme): 'light' | 'dark' => {
  return theme === 'system' ? getSystemTheme() : theme
}

const applyTheme = (resolvedTheme: 'light' | 'dark') => {
  document.documentElement.classList.remove('light', 'dark')
  document.documentElement.classList.add(resolvedTheme)
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set, get) => ({
      theme: 'system',
      resolvedTheme: getSystemTheme(),
      setTheme: (theme) => {
        const resolved = resolveTheme(theme)
        applyTheme(resolved)
        set({ theme, resolvedTheme: resolved })
      },
      toggleTheme: () => {
        const newTheme = get().resolvedTheme === 'light' ? 'dark' : 'light'
        applyTheme(newTheme)
        set({ theme: newTheme, resolvedTheme: newTheme })
      },
    }),
    {
      name: 'theme-storage',
      partialize: (state) => ({ theme: state.theme }),
      onRehydrateStorage: () => (state) => {
        if (state) {
          const resolved = resolveTheme(state.theme)
          applyTheme(resolved)
          state.resolvedTheme = resolved
        }
      },
    }
  )
)

export const initializeTheme = () => {
  const { theme } = useThemeStore.getState()
  const resolved = resolveTheme(theme)
  applyTheme(resolved)
  useThemeStore.setState({ resolvedTheme: resolved })

  // Listen for system preference changes
  const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
  mediaQuery.addEventListener('change', () => {
    if (useThemeStore.getState().theme === 'system') {
      const newResolved = getSystemTheme()
      applyTheme(newResolved)
      useThemeStore.setState({ resolvedTheme: newResolved })
    }
  })
}
