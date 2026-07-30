import { Suspense, lazy } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { useAppStore } from './shared/store/appStore'
import Landing        from './shared/components/Landing'
import AuthCallback   from './shared/components/AuthCallback'
import { TabFallback } from './shared/components/ui'

// The authenticated shell is lazy so an anonymous visitor at "/" does not download
// it. Landing is one text field and one button, but these static imports pulled in
// Layout -> Sidebar + Topbar -> MUI Menu, 16 icons, react-query and the api client,
// which put ~269 KB gzipped in the first-paint graph.
const Layout    = lazy(() => import('./shared/components/layout/Layout'))
const Dashboard = lazy(() => import('./shared/components/layout/Dashboard'))

export default function App() {
  // Accept both Google-authed users (isAuthenticated) and legacy PAN-only users (pan)
  const isAuthenticated = useAppStore((s) => s.isAuthenticated)
  const pan             = useAppStore((s) => s.pan)
  const authed          = isAuthenticated || !!pan

  return (
    <Suspense fallback={<TabFallback />}>
      <Routes>
        <Route path="/"               element={authed ? <Navigate to="/dashboard" replace /> : <Landing />} />
        {/* Google OAuth redirect handler — always accessible, no auth required */}
        <Route path="/auth/callback"  element={<AuthCallback />} />
        <Route path="/dashboard/*"    element={authed ? <Layout><Dashboard /></Layout> : <Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  )
}
