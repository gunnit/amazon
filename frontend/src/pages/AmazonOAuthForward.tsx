import { useEffect } from 'react'
import { Loader2 } from 'lucide-react'

const API_URL = import.meta.env.VITE_API_URL || ''

// Safety net for the SP-API OAuth flow: if Amazon redirects the consent
// response to the frontend (first registered redirect URI) instead of the
// backend callback, forward the full query string to the backend so the
// code exchange still happens. Must stay a public route.
export default function AmazonOAuthForward() {
  useEffect(() => {
    window.location.replace(
      `${API_URL}/api/v1/accounts/oauth/callback${window.location.search}`
    )
  }, [])

  return (
    <div className="flex h-screen items-center justify-center">
      <Loader2 className="h-8 w-8 animate-spin text-primary" />
    </div>
  )
}
