import { useEffect, useRef, useState } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from '@/store/authStore'
import { Toaster } from '@/components/ui/toaster'
import Layout from '@/components/Layout'
import Login from '@/pages/Login'
import Register from '@/pages/Register'
import Dashboard from '@/pages/Dashboard'
import Reports from '@/pages/Reports'
import Analytics from '@/pages/Analytics'
import Forecasts from '@/pages/Forecasts'
import MarketResearch from '@/pages/MarketResearch'
import Catalog from '@/pages/Catalog'
import Recommendations from '@/pages/Recommendations'
import Settings from '@/pages/Settings'
import Alerts from '@/pages/Alerts'

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuthStore()

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  return <>{children}</>
}

function App() {
  const { isAuthenticated, loadUser, logout } = useAuthStore()
  const [authChecked, setAuthChecked] = useState(false)
  const hasBootstrappedAuth = useRef(false)

  useEffect(() => {
    if (hasBootstrappedAuth.current) {
      return
    }

    hasBootstrappedAuth.current = true
    let isMounted = true

    const bootstrapAuth = async () => {
      const token = localStorage.getItem('access_token')

      if (!token) {
        logout()
        if (isMounted) {
          setAuthChecked(true)
        }
        return
      }

      try {
        await loadUser()
      } finally {
        if (isMounted) {
          setAuthChecked(true)
        }
      }
    }

    void bootstrapAuth()

    return () => {
      isMounted = false
    }
  }, [loadUser, logout])

  if (!authChecked) {
    return null
  }

  return (
    <>
      <Routes>
        <Route path="/login" element={
          isAuthenticated ? <Navigate to="/" replace /> : <Login />
        } />
        <Route path="/register" element={
          isAuthenticated ? <Navigate to="/" replace /> : <Register />
        } />

        <Route path="/" element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }>
          <Route index element={<Dashboard />} />
          <Route path="accounts" element={<Navigate to="/settings?tab=accounts" replace />} />
          <Route path="reports" element={<Reports />} />
          <Route path="analytics" element={<Analytics />} />
          <Route path="forecasts" element={<Forecasts />} />
          <Route path="market-research" element={<MarketResearch />} />
          <Route path="catalog" element={<Catalog />} />
          <Route path="recommendations" element={<Recommendations />} />
          <Route path="alerts" element={<Alerts />} />
          <Route path="settings" element={<Settings />} />
        </Route>
      </Routes>
      <Toaster />
    </>
  )
}

export default App
