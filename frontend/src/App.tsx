import { Routes, Route, Navigate } from 'react-router-dom'
import { usePan } from './store/appStore'
import Layout    from './components/layout/Layout'
import Landing   from './components/Landing'
import Dashboard from './components/layout/Dashboard'

export default function App() {
  const pan = usePan()
  return (
    <Routes>
      <Route path="/" element={pan ? <Navigate to="/dashboard" replace /> : <Landing />} />
      <Route path="/dashboard/*" element={pan ? <Layout><Dashboard /></Layout> : <Navigate to="/" replace />} />
    </Routes>
  )
}
