import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import Layout from './components/Layout'
import { useAuth } from './context/AuthContext'
import { Spinner } from './components/Icon'
import Login from './pages/Login'
import Overview from './pages/Overview'
import Instances from './pages/Instances'
import InstanceDetail from './pages/InstanceDetail'
import Monitoring from './pages/Monitoring'
import Security from './pages/Security'
import Costs from './pages/Costs'
import Logs from './pages/Logs'
import Incidents from './pages/Incidents'
import Remediation from './pages/Remediation'
import Pipelines from './pages/Pipelines'
import Aws from './pages/Aws'
import Audit from './pages/Audit'
import Settings from './pages/Settings'

function FullPageSpinner() {
  return (
    <div className="flex min-h-screen items-center justify-center gap-3 bg-slate-100 text-sm text-slate-500 dark:bg-slate-950 dark:text-slate-400">
      <Spinner size={18} /> Loading CloudOps Sentinel…
    </div>
  )
}

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) return <FullPageSpinner />
  if (!user) return <Navigate to="/login" state={{ from: location.pathname }} replace />
  return <>{children}</>
}

function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-24 text-center">
      <p className="text-3xl font-semibold text-slate-800 dark:text-slate-100">404</p>
      <p className="text-sm text-slate-500 dark:text-slate-400">That page does not exist in CloudOps Sentinel.</p>
      <a href="/" className="btn btn-primary mt-2">
        Back to overview
      </a>
    </div>
  )
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route index element={<Overview />} />
        <Route path="/instances" element={<Instances />} />
        <Route path="/instances/:id" element={<InstanceDetail />} />
        <Route path="/monitoring" element={<Monitoring />} />
        <Route path="/security" element={<Security />} />
        <Route path="/costs" element={<Costs />} />
        <Route path="/logs" element={<Logs />} />
        <Route path="/incidents" element={<Incidents />} />
        <Route path="/remediation" element={<Remediation />} />
        <Route path="/pipelines" element={<Pipelines />} />
        <Route path="/aws" element={<Aws />} />
        <Route path="/audit" element={<Audit />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}
