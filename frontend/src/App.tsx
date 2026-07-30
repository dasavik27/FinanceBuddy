import { Suspense, lazy } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { usePan } from './shared/store/appStore'
import Landing   from './shared/components/Landing'
import { TabFallback } from './shared/components/ui'

// The authenticated shell is lazy so an anonymous visitor at "/" does not download
// it. Landing is one text field and one button, but these static imports pulled in
// Layout -> Sidebar + Topbar -> MUI Menu, 16 icons, react-query and the api client,
// which put ~269 KB gzipped in the first-paint graph.
const Layout    = lazy(() => import('./shared/components/layout/Layout'))
const Dashboard = lazy(() => import('./shared/components/layout/Dashboard'))

export default function App() {
  const pan = usePan()
  // A skeleton fallback rather than null: `null` renders a blank white screen for
  // however long the dashboard chunk takes to arrive, which reads as a broken app on a
  // slow connection.
  return (
    <Suspense fallback={<TabFallback />}>
      <Routes>
        <Route path="/" element={pan ? <Navigate to="/dashboard" replace /> : <Landing />} />
        <Route path="/dashboard/*" element={pan ? <Layout><Dashboard /></Layout> : <Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  )
}
