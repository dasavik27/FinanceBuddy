import { Routes, Route, Navigate } from 'react-router-dom'
import { usePan } from './shared/store/appStore'
import Layout    from './shared/components/layout/Layout'
import Landing   from './shared/components/Landing'
import Dashboard from './shared/components/layout/Dashboard'

export default function App() {
  const pan = usePan()
  return (
    <Routes>
      <Route path="/" element={pan ? <Navigate to="/dashboard" replace /> : <Landing />} />
      <Route path="/dashboard/*" element={pan ? <Layout><Dashboard /></Layout> : <Navigate to="/" replace />} />
    </Routes>
  )
}
