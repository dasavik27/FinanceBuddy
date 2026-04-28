import { Routes, Route, Navigate } from 'react-router-dom'
import { useSessionId } from './store/appStore'
import Layout    from './components/Layout'
import Landing   from './components/Landing'
import Dashboard from './components/Dashboard'

export default function App() {
  const sid = useSessionId()
  return (
    <Routes>
      <Route path="/" element={sid ? <Navigate to="/dashboard" replace /> : <Landing />} />
      <Route path="/dashboard/*" element={sid ? <Layout><Dashboard /></Layout> : <Navigate to="/" replace />} />
    </Routes>
  )
}
