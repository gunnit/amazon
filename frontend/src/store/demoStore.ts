import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface DemoState {
  mockDataEnabled: boolean
  setMockDataEnabled: (enabled: boolean) => void
  toggleMockData: () => void
}

const getStoredMockFlag = (): boolean => {
  if (typeof window === 'undefined') return false
  const raw = localStorage.getItem('demo-storage')
  if (!raw) return false
  try {
    const parsed = JSON.parse(raw) as { state?: { mockDataEnabled?: boolean } }
    return Boolean(parsed?.state?.mockDataEnabled)
  } catch {
    return false
  }
}

export const useDemoStore = create<DemoState>()(
  persist(
    (set, get) => ({
      mockDataEnabled: false,
      setMockDataEnabled: (enabled) => set({ mockDataEnabled: enabled }),
      toggleMockData: () => set({ mockDataEnabled: !get().mockDataEnabled }),
    }),
    {
      name: 'demo-storage',
      partialize: (state) => ({ mockDataEnabled: state.mockDataEnabled }),
    }
  )
)

export const isMockDataEnabled = (): boolean => {
  const stored = getStoredMockFlag()
  return stored || useDemoStore.getState().mockDataEnabled
}
