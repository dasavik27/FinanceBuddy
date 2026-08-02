import { Suspense, lazy, useEffect, useState } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { useAppStore, useIsAuthenticated } from './shared/store/appStore'
import authClient from './shared/auth/authClient'
import { apiClient } from './shared/api/client'
import Landing   from './shared/components/Landing'
import { TabFallback } from './shared/components/ui'

// The authenticated shell is lazy so an anonymous visitor at "/" does not download
// it. Landing is one text field and one button, but these static imports pulled in
// Layout -> Sidebar + Topbar -> MUI Menu, 16 icons, react-query and the api client,
// which put ~269 KB gzipped in the first-paint graph.
const Layout    = lazy(() => import('./shared/components/layout/Layout'))
const Dashboard = lazy(() => import('./shared/components/layout/Dashboard'))

export default function App() {
  const isAuthenticated = useIsAuthenticated()
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
    const unsubscribe = authClient.onAuthStateChange((user) => {
      if (user) {
        setIdentity({ userId: user.id, email: user.email })
        apiClient.getMe().then((me: { pan: string | null }) => {
          setIdentity({ userId: user.id, email: user.email, pan: me.pan })
        }).catch((e: unknown) => console.error('Failed to fetch profile', e))
      } else {
        clearIdentity()
      }
      setResolvingSession(false)
    })
    return unsubscribe
  }, [setIdentity, clearIdentity])

  if (resolvingSession) return <TabFallback />
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
