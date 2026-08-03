import { Suspense, lazy, useEffect, useState } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { useAppStore, useIsAuthenticated } from './shared/store/appStore'
import authClient, { REQUEST_ACCESS_MESSAGE } from './shared/auth/authClient'
import { apiClient } from './shared/api/client'
import Landing   from './shared/components/Landing'
import MandatoryPanPrompt from './shared/components/MandatoryPanPrompt'
import PendingAccess from './shared/components/PendingAccess'
import SuspendedAccess from './shared/components/SuspendedAccess'
import { TabFallback } from './shared/components/ui'

const AUTH_NOTICE_KEY = 'fb_auth_notice'

function isNotAuthorizedError(e: unknown): { message: string } | null {
  const err = e as { response?: { status?: number; data?: { detail?: string; message?: string } } }
  if (err?.response?.status !== 403) return null
  if (err.response.data?.detail !== 'not_authorized') return null
  return { message: REQUEST_ACCESS_MESSAGE }
}

// The authenticated shell is lazy so an anonymous visitor at "/" does not download
// it. Landing is one text field and one button, but these static imports pulled in
// Layout -> Sidebar + Topbar -> MUI Menu, 16 icons, react-query and the api client,
// which put ~269 KB gzipped in the first-paint graph.
const Layout    = lazy(() => import('./shared/components/layout/Layout'))
const Dashboard = lazy(() => import('./shared/components/layout/Dashboard'))

export default function App() {
  const isAuthenticated = useIsAuthenticated()
  const pan = useAppStore((s) => s.pan)
  const status = useAppStore((s) => s.status)
  const setIdentity = useAppStore((s) => s.setIdentity)
  const clearIdentity = useAppStore((s) => s.clearIdentity)

  // Until the provider has been asked whether a session exists, we do not know
  // whether this visitor is signed in. Rendering the route table immediately would
  // bounce a returning user to the landing page for a frame before redirecting them
  // back - and on a slow load, long enough to click something.
  const [resolvingSession, setResolvingSession] = useState(authClient.isConfigured)

  useEffect(() => {
    if (!authClient.isConfigured) return

    // Fires once on mount with the restored session (or null), then on every
    // sign-in, sign-out and token refresh.
    const unsubscribe = authClient.onAuthStateChange(async (user) => {
      if (user) {
        setIdentity({ userId: user.id, email: user.email })
        try {
          const me = await apiClient.getMe()
          setIdentity({
            userId: user.id,
            email: user.email,
            pan: me.pan,
            status: me.status,
            role: me.role,
          })
        } catch (e: unknown) {
          const unauthorized = isNotAuthorizedError(e)
          if (unauthorized) {
            sessionStorage.setItem(AUTH_NOTICE_KEY, unauthorized.message)
            await authClient.signOut()
            clearIdentity()
          } else {
            console.error('Failed to fetch profile', e)
            // Avoid an infinite loading shell if /auth/me blips; PAN gate still applies
            // from persisted pan when present.
            setIdentity({ userId: user.id, email: user.email, status: 'active' })
          }
        }
      } else {
        clearIdentity()
      }
      setResolvingSession(false)
    })
    return unsubscribe
  }, [setIdentity, clearIdentity])

  if (resolvingSession) return <TabFallback />

  // Profile (status/role) is loaded after the Supabase session; wait so we do not
  // flash the dashboard before pending / not_authorized / PAN gates apply.
  if (isAuthenticated && !status) {
    return <TabFallback />
  }

  if (isAuthenticated && status === 'suspended') {
    return <SuspendedAccess />
  }

  if (isAuthenticated && status === 'pending') {
    return <PendingAccess />
  }

  // If the user has authenticated with Google/Supabase but has not registered a PAN,
  // PAN registration is compulsory before dashboard access is permitted.
  if (isAuthenticated && !pan) {
    return <MandatoryPanPrompt />
  }

  // A skeleton fallback rather than null: `null` renders a blank white screen for
  // however long the dashboard chunk takes to arrive, which reads as a broken app on a
  // slow connection.
  return (
    <Suspense fallback={<TabFallback />}>
      <Routes>
        <Route path="/" element={isAuthenticated ? <Navigate to="/dashboard" replace /> : <Landing />} />
        {/* Every authenticated route lives at the top level: /equity, /budget,
            /tax-expert, /mutual-funds, /accounts, and /dashboard for the hub. This
            was "/dashboard/*", which made every domain a child of a segment that
            named none of them. Dashboard keeps the legacy /dashboard/<domain>
            redirects so existing links and bookmarks still resolve. */}
        <Route path="/*" element={isAuthenticated ? <Layout><Dashboard /></Layout> : <Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  )
}
