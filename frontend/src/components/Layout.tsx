import { useEffect, useRef, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useTheme } from '../context/ThemeContext'
import { platformApi } from '../api/endpoints'
import { timeAgo } from '../lib/format'
import type { NotificationItem, RuntimeInfo } from '../types'
import { Icon } from './Icon'

const PAGE_TITLES: Record<string, string> = {
  '/': 'Overview',
  '/instances': 'Infrastructure',
  '/monitoring': 'Monitoring',
  '/security': 'Security findings',
  '/costs': 'Cost optimization',
  '/logs': 'Log intelligence',
  '/incidents': 'Incidents',
  '/remediation': 'Remediation',
  '/pipelines': 'CI/CD pipelines',
  '/aws': 'AWS integrations',
  '/audit': 'Audit logs',
  '/settings': 'Settings',
}

const NAV = [
  {
    section: 'Operations',
    items: [
      { to: '/', label: 'Overview', icon: 'home' },
      { to: '/instances', label: 'Infrastructure', icon: 'server' },
      { to: '/monitoring', label: 'Monitoring', icon: 'activity' },
      { to: '/incidents', label: 'Incidents', icon: 'alert' },
    ],
  },
  {
    section: 'Reliability',
    items: [
      { to: '/security', label: 'Security', icon: 'shield' },
      { to: '/logs', label: 'Log Intelligence', icon: 'file' },
      { to: '/remediation', label: 'Remediation', icon: 'wrench' },
      { to: '/pipelines', label: 'CI/CD Pipelines', icon: 'git' },
    ],
  },
  {
    section: 'Cloud & Governance',
    items: [
      { to: '/costs', label: 'Cost Optimization', icon: 'dollar' },
      { to: '/aws', label: 'AWS Integrations', icon: 'cloud' },
      { to: '/audit', label: 'Audit Logs', icon: 'list' },
      { to: '/settings', label: 'Settings', icon: 'settings' },
    ],
  },
]

export default function Layout() {
  const { user, logout, canOperate } = useAuth()
  const { theme, toggle } = useTheme()
  const navigate = useNavigate()
  const location = useLocation()
  const [mobileOpen, setMobileOpen] = useState(false)
  const [notifications, setNotifications] = useState<NotificationItem[]>([])
  const [bellOpen, setBellOpen] = useState(false)
  const [runtime, setRuntime] = useState<RuntimeInfo | null>(null)
  const [search, setSearch] = useState('')
  const bellRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    setMobileOpen(false)
    setBellOpen(false)
    const base = location.pathname.startsWith('/instances/') ? 'Instance detail' : PAGE_TITLES[location.pathname]
    document.title = base ? `${base} · CloudOps Sentinel` : 'CloudOps Sentinel'
  }, [location.pathname])

  useEffect(() => {
    platformApi
      .runtime()
      .then(setRuntime)
      .catch(() => setRuntime(null))
    const load = () =>
      platformApi
        .notifications(20)
        .then(setNotifications)
        .catch(() => undefined)
    void load()
    const timer = window.setInterval(load, 60_000)
    return () => window.clearInterval(timer)
  }, [])

  useEffect(() => {
    function onClick(event: MouseEvent) {
      if (bellRef.current && !bellRef.current.contains(event.target as Node)) setBellOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  const unread = notifications.filter((item) => !item.is_read).length

  async function markAllRead() {
    await platformApi.markAllRead().catch(() => undefined)
    setNotifications((current) => current.map((item) => ({ ...item, is_read: true })))
  }

  function submitSearch(event: React.FormEvent) {
    event.preventDefault()
    if (!search.trim()) return
    navigate(`/logs?q=${encodeURIComponent(search.trim())}`)
    setSearch('')
  }

  return (
    <div className="min-h-screen bg-slate-100 dark:bg-slate-950">
      {/* sidebar */}
      <aside
        className={`fixed inset-y-0 left-0 z-40 w-60 transform border-r bg-white transition-transform duration-200 dark:bg-slate-900 lg:translate-x-0 ${
          mobileOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="flex h-full flex-col">
          <Link to="/" className="flex items-center gap-2.5 border-b px-4 py-4">
            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-brand-500 to-indigo-600 text-white shadow-md">
              <Icon name="cloud" size={18} />
            </span>
            <span>
              <span className="block text-[13.5px] font-semibold leading-tight text-slate-900 dark:text-slate-50">CloudOps</span>
              <span className="block text-[11px] font-medium uppercase tracking-[0.18em] text-brand-600 dark:text-brand-400">Sentinel</span>
            </span>
          </Link>

          <nav className="flex-1 space-y-5 overflow-y-auto px-2.5 py-4">
            {NAV.map((group) => (
              <div key={group.section}>
                <p className="mb-1.5 px-2.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-400 dark:text-slate-500">
                  {group.section}
                </p>
                <div className="space-y-0.5">
                  {group.items.map((item) => (
                    <NavLink
                      key={item.to}
                      to={item.to}
                      end={item.to === '/'}
                      className={({ isActive }) => `nav-link ${isActive ? 'nav-link-active' : ''}`}
                    >
                      <Icon name={item.icon} size={15} />
                      <span>{item.label}</span>
                    </NavLink>
                  ))}
                </div>
              </div>
            ))}
          </nav>

          <div className="border-t p-3">
            <div className="rounded-lg border bg-slate-50 p-2.5 text-[11px] dark:bg-slate-950/60">
              <p className="flex items-center justify-between font-medium text-slate-600 dark:text-slate-300">
                <span>Runtime</span>
                <span className="badge badge-success">local</span>
              </p>
              <p className="mt-1 text-slate-500 dark:text-slate-400">
                AWS: <span className="font-medium">{runtime?.aws_mode ?? '…'}</span> · AI:{' '}
                <span className="font-medium">{runtime?.ai_enabled ? 'on' : 'off'}</span>
              </p>
              <p className="mt-1 text-slate-400">v{runtime?.version ?? '1.0.0'} · {runtime?.environment ?? 'local'}</p>
            </div>
          </div>
        </div>
      </aside>

      {mobileOpen && <div className="fixed inset-0 z-30 bg-slate-950/50 lg:hidden" onClick={() => setMobileOpen(false)} />}

      <div className="lg:pl-60">
        {/* top bar */}
        <header className="sticky top-0 z-20 border-b bg-white/85 backdrop-blur dark:bg-slate-900/85">
          <div className="flex h-14 items-center gap-3 px-4">
            <button type="button" className="btn btn-ghost btn-xs lg:hidden" onClick={() => setMobileOpen(true)} aria-label="Open navigation">
              <Icon name="list" size={16} />
            </button>

            <form onSubmit={submitSearch} className="relative hidden max-w-sm flex-1 sm:block">
              <span className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400">
                <Icon name="search" size={14} />
              </span>
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search logs, services, trace IDs…"
                aria-label="Search logs"
                className="input h-9 pl-8 pr-14 text-[13px]"
              />
              <span className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2">
                <span className="kbd">↵</span>
              </span>
            </form>

            <div className="ml-auto flex items-center gap-1.5">
              {runtime?.warnings && runtime.warnings.length > 0 && (
                <span className="badge badge-medium hidden md:inline-flex" title={runtime.warnings.join(' · ')}>
                  <Icon name="alert" size={11} /> setup warnings
                </span>
              )}
              <button type="button" className="btn btn-ghost btn-xs" onClick={toggle} aria-label="Toggle theme" title="Toggle theme">
                <Icon name={theme === 'dark' ? 'sun' : 'moon'} size={15} />
              </button>

              <div className="relative" ref={bellRef}>
                <button
                  type="button"
                  className="btn btn-ghost btn-xs relative"
                  onClick={() => setBellOpen((open) => !open)}
                  aria-label="Notifications"
                  aria-expanded={bellOpen}
                >
                  <Icon name="bell" size={15} />
                  {unread > 0 && (
                    <span className="absolute -right-0.5 -top-0.5 flex h-3.5 min-w-3.5 items-center justify-center rounded-full bg-rose-500 px-1 text-[9px] font-semibold text-white">
                      {unread > 9 ? '9+' : unread}
                    </span>
                  )}
                </button>
                {bellOpen && (
                  <div className="absolute right-0 mt-2 w-80 animate-fade-in overflow-hidden rounded-xl border bg-white shadow-xl dark:bg-slate-900">
                    <div className="flex items-center justify-between border-b px-3 py-2">
                      <p className="text-xs font-semibold text-slate-800 dark:text-slate-100">Notifications</p>
                      <button type="button" className="text-[11px] text-brand-600 hover:underline dark:text-brand-400" onClick={markAllRead}>
                        Mark all read
                      </button>
                    </div>
                    <div className="max-h-80 overflow-y-auto">
                      {notifications.length === 0 && <p className="px-3 py-6 text-center text-xs text-slate-500">No notifications yet.</p>}
                      {notifications.map((item) => (
                        <div key={item.id} className={`border-b px-3 py-2.5 text-xs ${item.is_read ? 'opacity-60' : ''}`}>
                          <div className="flex items-center justify-between gap-2">
                            <span className={`font-medium ${item.severity === 'critical' ? 'text-rose-600 dark:text-rose-300' : 'text-slate-800 dark:text-slate-100'}`}>
                              {item.title}
                            </span>
                            <span className="shrink-0 text-[10px] text-slate-400">{timeAgo(item.created_at)}</span>
                          </div>
                          <p className="mt-0.5 line-clamp-2 text-slate-500 dark:text-slate-400">{item.message}</p>
                        </div>
                      ))}
                    </div>
                    <Link to="/audit" className="block border-t px-3 py-2 text-center text-[11px] text-brand-600 hover:bg-slate-50 dark:text-brand-400 dark:hover:bg-slate-800">
                      View audit trail
                    </Link>
                  </div>
                )}
              </div>

              <div className="mx-1 h-5 w-px bg-slate-200 dark:bg-slate-700" />

              <div className="flex items-center gap-2">
                <span className="flex h-7 w-7 items-center justify-center rounded-full bg-brand-600 text-[11px] font-semibold text-white">
                  {(user?.full_name || user?.email || '?').slice(0, 2).toUpperCase()}
                </span>
                <div className="hidden leading-tight sm:block">
                  <p className="max-w-[150px] truncate text-[12px] font-medium text-slate-800 dark:text-slate-100">{user?.full_name}</p>
                  <p className="text-[10px] uppercase tracking-wide text-slate-500">{user?.role}{canOperate ? '' : ' · read-only'}</p>
                </div>
                <button type="button" className="btn btn-ghost btn-xs" onClick={logout} title="Sign out" aria-label="Sign out">
                  <Icon name="logout" size={14} />
                </button>
              </div>
            </div>
          </div>
        </header>

        <main className="mx-auto max-w-[1500px] px-4 py-5 sm:px-6">
          <Outlet />
        </main>

        <footer className="mx-auto max-w-[1500px] px-4 pb-6 pt-2 text-[11px] text-slate-400 sm:px-6">
          CloudOps Sentinel · local mode · simulated infrastructure is labelled wherever it appears · no cloud mutation is
          performed without explicit human approval
        </footer>
      </div>
    </div>
  )
}
