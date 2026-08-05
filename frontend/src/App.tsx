import { Suspense, lazy, useEffect, useState } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { useAppStore, useIsAuthenticated } from './shared/store/appStore'
import authClient, {
  type AccessRequestStatus,
  isPasswordSetupRequired,
  lookupAccessNoticeForEmails,
} from './shared/auth/authClient'
import { writeAuthNotice, readAccessRequestEmail } from './shared/auth/authNotice'
import { apiClient } from './shared/api/client'
import Landing   from './shared/components/Landing'
import AccountSetupPrompt from './shared/components/AccountSetupPrompt'
import PendingAccess from './shared/components/PendingAccess'
import SuspendedAccess from './shared/components/SuspendedAccess'
import { TabFallback } from './shared/components/ui'

function parseNotAuthorizedError(e: unknown): {
  message: string
  access_request_status: AccessRequestStatus
} | null {
  const err = e as {
    response?: {
      status?: number
      data?: {
        detail?: string
        message?: string
        access_request_status?: AccessRequestStatus
      }
    }
  }
  if (err?.response?.status !== 403) return null
  if (err.response.data?.detail !== 'not_authorized') return null
  return {
    message: err.response.data?.message || 'You do not have access yet.',
    access_request_status: err.response.data?.access_request_status || 'none',
  }
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
  const [needsPasswordSetup, setNeedsPasswordSetup] = useState(() => isPasswordSetupRequired())

  useEffect(() => {
    if (!authClient.isConfigured) return

    // Fires once on mount with the restored session (or null), then on sign-in /
    // sign-out (token refresh is ignored in authClient — no extra /auth/me).
    let cancelled = false
    const unsubscribe = authClient.onAuthStateChange(async (user) => {
      setNeedsPasswordSetup(isPasswordSetupRequired())
      if (user) {
        // Session already has id/email — skip authClient.getUser() (extra Supabase RTT).
        setIdentity({ userId: user.id, email: user.email })
        try {
          const me = await apiClient.getMe()
          if (cancelled) return
          // Never replace a PAN we already have with null from a stale /auth/me
          // (e.g. in-flight resolve that started before PUT /auth/profile/pan).
          const prev = useAppStore.getState()
          const keepPan =
            me.pan ?? (prev.userId === user.id || prev.userId === null ? prev.pan : null)
          setIdentity({
            userId: user.id,
            email: me.email ?? user.email,
            displayName: me.display_name,
            pan: keepPan,
            status: me.status,
            role: me.role,
          })
        } catch (e: unknown) {
          if (cancelled) return
          let notice = await lookupAccessNoticeForEmails([
            user.email,
            readAccessRequestEmail(),
          ])
          const unauthorized = parseNotAuthorizedError(e)
          if (notice.access_request_status === 'none' && unauthorized) {
            if (unauthorized.access_request_status !== 'none') {
              notice = {
                message: unauthorized.message,
                access_request_status: unauthorized.access_request_status,
                email: user.email,
              }
            } else {
              notice = { ...notice, message: unauthorized.message }
            }
          }
          writeAuthNotice(notice)
          await authClient.signOut()
          if (!cancelled) clearIdentity()
        }
      } else if (!cancelled) {
        clearIdentity()
      }
      if (!cancelled) setResolvingSession(false)
    })
    return () => {
      cancelled = true
      unsubscribe()
    }
  }, [setIdentity, clearIdentity])

  // Proactively verify session health when waking from sleep, focusing tab, or idle
  useEffect(() => {
    if (!isAuthenticated || !authClient.isConfigured) return

    let isChecking = false
    const verifySessionHealth = async () => {
      if (isChecking) return
      isChecking = true
      try {
        const isHealthy = await authClient.checkSessionHealth()
        if (!isHealthy) {
          console.warn('Session expired or invalidated after idle. Signing out...')
          await authClient.signOut()
          clearIdentity()
        }
      } catch (e) {
        console.warn('Session health check error:', e)
      } finally {
        isChecking = false
      }
    }

    const onVisible = () => {
      if (document.visibilityState === 'visible') {
        void verifySessionHealth()
      }
    }

    const interval = setInterval(verifySessionHealth, 2 * 60 * 1000)
    document.addEventListener('visibilitychange', onVisible)
    window.addEventListener('focus', onVisible)

    return () => {
      clearInterval(interval)
      document.removeEventListener('visibilitychange', onVisible)
      window.removeEventListener('focus', onVisible)
    }
  }, [isAuthenticated, clearIdentity])

  if (resolvingSession) return <TabFallback />

  // Wait for /auth/me so we know status + whether PAN is already set. Showing
  // password before that loaded caused a second PAN-only screen after submit.
  if (isAuthenticated && !status) {
    return <TabFallback />
  }

  // Single setup panel (AccountSetupPrompt). Fields shown depend on what is
  // still missing — both together, or only password, or only PAN. No second screen.
  const requirePassword = isAuthenticated && needsPasswordSetup
  const requirePan = isAuthenticated && status === 'active' && !pan

  if (isAuthenticated && status === 'suspended') {
    return <SuspendedAccess />
  }

  if (requirePassword || requirePan) {
    return (
      <AccountSetupPrompt
        requirePassword={requirePassword}
        requirePan={requirePan}
        onPasswordComplete={() => setNeedsPasswordSetup(false)}
      />
    )
  }

  if (isAuthenticated && status === 'pending') {
    return <PendingAccess />
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
