import { useEffect, useState } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from '@/store/authStore'
import { Toaster } from '@/components/ui/toaster'
import Layout from '@/components/Layout'
import { ErrorBoundary } from '@/components/ErrorBoundary'
import Login from '@/pages/Login'
import Register from '@/pages/Register'
import ForgotPassword from '@/pages/ForgotPassword'
import ResetPassword from '@/pages/ResetPassword'
import AmazonOAuthForward from '@/pages/AmazonOAuthForward'
import Dashboard from '@/pages/Dashboard'
import Performance from '@/pages/Performance'
import ProductAnalytics from '@/pages/ProductAnalytics'
import Forecasts from '@/pages/Forecasts'
import MarketResearch from '@/pages/MarketResearch'
import BrandAnalysis from '@/pages/BrandAnalysis'
import BrandIntelligence from '@/pages/BrandIntelligence'
import Catalog from '@/pages/Catalog'
import Recommendations from '@/pages/Recommendations'
import Settings from '@/pages/Settings'
import Advertising from '@/pages/Advertising'
import Alerts from '@/pages/Alerts'
import Accounts from '@/pages/Accounts'
import NotFound from '@/pages/NotFound'

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

  useEffect(() => {
    const bootstrapAuth = async () => {
      const token = localStorage.getItem('access_token')

      if (!token) {
        logout()
        setAuthChecked(true)
        return
      }

      try {
        await loadUser()
      } finally {
        setAuthChecked(true)
      }
    }

    void bootstrapAuth()
  }, [loadUser, logout])

  if (!authChecked) {
    return null
  }

  return (
    <ErrorBoundary>
      <Routes>
        <Route path="/login" element={
          isAuthenticated ? <Navigate to="/" replace /> : <Login />
        } />
        <Route path="/register" element={
          isAuthenticated ? <Navigate to="/" replace /> : <Register />
        } />
        <Route path="/forgot-password" element={
          isAuthenticated ? <Navigate to="/" replace /> : <ForgotPassword />
        } />
        <Route path="/reset-password" element={
          isAuthenticated ? <Navigate to="/" replace /> : <ResetPassword />
        } />
        <Route path="/amazon/callback" element={<AmazonOAuthForward />} />

        <Route path="/" element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }>
          <Route index element={<Dashboard />} />
          <Route path="accounts" element={<Accounts />} />
          <Route path="performance" element={<Performance />} />
          <Route path="reports" element={<Navigate to="/performance" replace />} />
          <Route path="analytics" element={<Navigate to="/performance" replace />} />
          <Route path="analytics/product/:asin" element={<ProductAnalytics />} />
          <Route path="advertising" element={<Advertising />} />
          <Route path="forecasts" element={<Forecasts />} />
          <Route path="market-research" element={<MarketResearch />} />
          <Route
            path="brand-analysis"
            element={
              <ErrorBoundary title="Brand Analysis crashed">
                <BrandAnalysis />
              </ErrorBoundary>
            }
          />
          <Route
            path="brand-intelligence"
            element={
              <ErrorBoundary title="Brand Intelligence crashed">
                <BrandIntelligence />
              </ErrorBoundary>
            }
          />
          {/* Old Brand Pulse path redirects to the repositioned reader. */}
          <Route path="brand-pulse" element={<Navigate to="/brand-intelligence" replace />} />
          <Route path="catalog" element={<Catalog />} />
          <Route path="recommendations" element={<Recommendations />} />
          <Route path="alerts" element={<Alerts />} />
          <Route path="settings" element={<Settings />} />
          <Route path="*" element={<NotFound />} />
        </Route>

        <Route
          path="*"
          element={isAuthenticated ? <Navigate to="/" replace /> : <Navigate to="/login" replace />}
        />
      </Routes>
      <Toaster />
    </ErrorBoundary>
  )
}

export default App
