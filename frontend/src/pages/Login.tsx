import { useEffect, useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { Icon, Spinner } from '../components/Icon'

const HIGHLIGHTS = [
  { icon: 'activity', title: 'Live telemetry', text: 'psutil host metrics plus a clearly labelled simulated fleet.' },
  { icon: 'shield', title: 'Security posture', text: 'S3, IAM, security-group and IaC checks with downloadable reports.' },
  { icon: 'dollar', title: 'Cost intelligence', text: 'Idle and oversized resource detection from real utilisation.' },
  { icon: 'wrench', title: 'Safe remediation', text: 'Allowlisted actions, dry-run first, human approval for production.' },
]

export default function Login() {
  const { login, user, loading, error } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [localError, setLocalError] = useState<string | null>(null)

  useEffect(() => {
    document.title = 'Sign in · CloudOps Sentinel'
  }, [])

  if (user) return <Navigate to="/" replace />

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault()
    setSubmitting(true)
    setLocalError(null)
    try {
      await login(email, password)
      navigate('/', { replace: true })
    } catch {
      /* error message is surfaced from context */
    } finally {
      setSubmitting(false)
    }
  }

  const message = localError || error

  return (
    <div className="grid min-h-screen lg:grid-cols-[1.1fr_1fr]">
      <div className="relative hidden flex-col justify-between overflow-hidden bg-slate-950 p-10 text-slate-200 lg:flex">
        <div className="absolute -left-24 -top-24 h-80 w-80 rounded-full bg-brand-600/30 blur-3xl" />
        <div className="absolute -bottom-32 right-0 h-96 w-96 rounded-full bg-indigo-600/20 blur-3xl" />

        <div className="relative flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-brand-500 to-indigo-600 shadow-lg">
            <Icon name="cloud" size={20} />
          </span>
          <div>
            <p className="text-sm font-semibold">CloudOps Sentinel</p>
            <p className="text-[11px] uppercase tracking-[0.2em] text-brand-300">Cloud operations platform</p>
          </div>
        </div>

        <div className="relative max-w-lg">
          <h1 className="text-3xl font-semibold leading-tight text-white">
            Monitor, secure and stabilise your cloud — from one control plane.
          </h1>
          <p className="mt-3 text-sm leading-relaxed text-slate-400">
            Infrastructure telemetry, security findings, cost intelligence, log analysis, incident response and
            approval-gated remediation. Runs fully in local mode with no paid services required.
          </p>

          <div className="mt-8 grid gap-3 sm:grid-cols-2">
            {HIGHLIGHTS.map((item) => (
              <div key={item.title} className="rounded-lg border border-white/10 bg-white/5 p-3">
                <span className="flex items-center gap-2 text-[13px] font-medium text-white">
                  <Icon name={item.icon} size={15} className="text-brand-300" /> {item.title}
                </span>
                <p className="mt-1 text-[11.5px] leading-relaxed text-slate-400">{item.text}</p>
              </div>
            ))}
          </div>
        </div>

        <p className="relative text-[11px] text-slate-500">
          Simulated data is always labelled. No destructive cloud operation is ever executed automatically.
        </p>
      </div>

      <div className="flex items-center justify-center bg-slate-100 px-6 py-12 dark:bg-slate-950">
        <div className="w-full max-w-sm">
          <div className="mb-6 lg:hidden">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-600 text-white">
              <Icon name="cloud" size={20} />
            </span>
          </div>
          <h2 className="text-xl font-semibold text-slate-900 dark:text-slate-50">Sign in</h2>
          <p className="mt-1 text-[13px] text-slate-500 dark:text-slate-400">
            Use your CloudOps Sentinel account. Sessions last 8 hours.
          </p>

          <form onSubmit={onSubmit} className="mt-6 space-y-4">
            <label className="block">
              <span className="label">Email</span>
              <input
                type="email"
                required
                autoComplete="username"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                className="input"
                placeholder="you@company.com"
              />
            </label>

            <label className="block">
              <span className="label">Password</span>
              <input
                type="password"
                required
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="input"
                placeholder="••••••••"
              />
            </label>

            {message && (
              <div role="alert" className="rounded-lg border border-rose-300 bg-rose-50 px-3 py-2 text-xs text-rose-700 dark:border-rose-500/40 dark:bg-rose-950/50 dark:text-rose-200">
                {message}
              </div>
            )}

            <button type="submit" className="btn btn-primary w-full py-2" disabled={submitting || loading}>
              {submitting ? <Spinner size={14} /> : <Icon name="logout" size={14} className="rotate-180" />}
              {submitting ? 'Signing in…' : 'Sign in'}
            </button>
          </form>

          {import.meta.env.DEV && (
            <div className="mt-6 rounded-lg border border-dashed px-3 py-2.5 text-[11px] leading-relaxed text-slate-500 dark:text-slate-400">
              <p className="font-medium text-slate-600 dark:text-slate-300">Seeded local accounts</p>
              <p className="mt-1 font-mono">admin@cloudops.local · engineer@cloudops.local</p>
              <p className="font-mono">analyst@cloudops.local</p>
              <p className="mt-1">Passwords come from DEFAULT_ADMIN_PASSWORD / DEFAULT_ANALYST_PASSWORD in your .env.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
