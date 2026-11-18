import { useState } from 'react'
import { authApi, platformApi } from '../api/endpoints'
import { useApi } from '../hooks/useApi'
import { useAuth } from '../context/AuthContext'
import { useTheme } from '../context/ThemeContext'
import { useToast } from '../context/ToastContext'
import { Card, DataNote, ErrorState, Field, Loading, Modal, PageHeader, StatCard } from '../components/ui'
import { Icon, Spinner } from '../components/Icon'
import { errorMessage } from '../api/client'
import { formatBytes, formatDateTime } from '../lib/format'

export default function Settings() {
  const { user, isAdmin, refresh } = useAuth()
  const toast = useToast()
  const { theme, setTheme } = useTheme()

  const [retention, setRetention] = useState<number | ''>('')
  const [savingRetention, setSavingRetention] = useState(false)
  const [pwdOpen, setPwdOpen] = useState(false)
  const [passwords, setPasswords] = useState({ current: '', next: '', confirm: '' })
  const [userOpen, setUserOpen] = useState(false)
  const [newUser, setNewUser] = useState({ email: '', full_name: '', password: '', role: 'viewer' })
  const [busy, setBusy] = useState(false)

  const runtime = useApi(() => platformApi.runtime(), [])
  const users = useApi(() => authApi.users(), [], { enabled: isAdmin || user?.role === 'engineer' })

  async function saveRetention(event: React.FormEvent) {
    event.preventDefault()
    setSavingRetention(true)
    try {
      const value = retention === '' ? runtime.data?.log_retention_days ?? 14 : Number(retention)
      await platformApi.updateRetention(value)
      toast.success(`Retention set to ${value} days`)
      runtime.reload()
      setRetention('')
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setSavingRetention(false)
    }
  }

  async function runCleanup() {
    if (!window.confirm('Delete log records outside the retention window?')) return
    try {
      const result = await platformApi.cleanup()
      toast.success(`Purged ${result.deleted} records (${result.retention_days} day window)`)
    } catch (err) {
      toast.error(errorMessage(err))
    }
  }

  async function changePassword(event: React.FormEvent) {
    event.preventDefault()
    if (passwords.next !== passwords.confirm) {
      toast.error('New passwords do not match')
      return
    }
    setBusy(true)
    try {
      await authApi.changePassword(passwords.current, passwords.next)
      toast.success('Password updated')
      setPwdOpen(false)
      setPasswords({ current: '', next: '', confirm: '' })
      await refresh()
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  async function createUser(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    try {
      await authApi.createUser(newUser)
      toast.success(`User ${newUser.email} created`)
      setUserOpen(false)
      setNewUser({ email: '', full_name: '', password: '', role: 'viewer' })
      users.reload()
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  async function toggleUser(id: number, active: boolean) {
    try {
      await authApi.setUserActive(id, active)
      toast.success(`User ${active ? 'activated' : 'deactivated'}`)
      users.reload()
    } catch (err) {
      toast.error(errorMessage(err))
    }
  }

  if (runtime.loading && !runtime.data) {
    return <div><PageHeader title="Settings" /><Loading rows={6} /></div>
  }
  if (runtime.error || !runtime.data) {
    return <div><PageHeader title="Settings" /><ErrorState message={runtime.error ?? 'Unavailable'} onRetry={runtime.reload} /></div>
  }

  const info = runtime.data

  return (
    <div className="space-y-4">
      <PageHeader
        title="Settings"
        subtitle="Runtime configuration, tooling availability, retention and user administration."
        actions={
          <button type="button" className="btn btn-secondary" onClick={() => setPwdOpen(true)}>
            <Icon name="shield" size={13} /> Change password
          </button>
        }
      />

      {info.warnings.length > 0 && (
        <div className="rounded-xl border border-amber-400/50 bg-amber-50 px-4 py-3 text-[12px] text-amber-800 dark:border-amber-500/30 dark:bg-amber-950/30 dark:text-amber-200">
          <p className="font-semibold">Setup warnings</p>
          <ul className="mt-1 list-inside list-disc space-y-0.5">
            {info.warnings.map((warning) => <li key={warning}>{warning}</li>)}
          </ul>
          <p className="mt-1 text-[11px] opacity-80">Set these values in .env before using this build in a shared environment.</p>
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard label="Version" value={info.version} hint={`${info.product} · ${info.environment}`} icon="cloud" tone="info" />
        <StatCard label="Database" value={info.database} hint={info.database_url_masked} icon="database" tone="default" />
        <StatCard label="Scheduler" value={info.scheduler_enabled ? 'on' : 'off'} hint={`Every ${info.monitoring_interval_seconds}s · collector ${info.local_collector ? 'on' : 'off'}`} icon="clock" tone={info.scheduler_enabled ? 'success' : 'warning'} />
        <StatCard label="AWS mode" value={info.aws_mode} hint={info.aws_region} icon="cloud" tone={info.aws_mode === 'simulated' ? 'warning' : 'success'} />
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card title="Application" subtitle="Effective configuration of the running process">
          <dl className="grid grid-cols-2 gap-3 text-[12px]">
            <div><dt className="text-slate-500">Environment</dt><dd className="font-medium">{info.environment}</dd></div>
            <div><dt className="text-slate-500">Database size</dt><dd className="font-medium">{info.database_size_bytes ? formatBytes(info.database_size_bytes) : 'n/a'}</dd></div>
            <div><dt className="text-slate-500">AI analysis</dt><dd className="font-medium">{info.ai_enabled ? `${info.ai_provider} enabled` : 'rule-based only'}</dd></div>
            <div><dt className="text-slate-500">Log retention</dt><dd className="font-medium">{info.log_retention_days} days</dd></div>
            <div className="col-span-2"><dt className="text-slate-500">CORS origins</dt><dd className="font-mono text-[11px]">{info.cors_origins.join(', ')}</dd></div>
          </dl>
          <DataNote>
            Configuration is environment driven. Secrets (SECRET_KEY, database password, AI key) are never returned by the API.
          </DataNote>
        </Card>

        <Card title="Tooling detected" subtitle="Optional scanners and deployment tools in this environment">
          <div className="grid grid-cols-2 gap-2">
            {Object.entries(info.tools).map(([tool, available]) => (
              <div key={tool} className="flex items-center justify-between rounded-lg border px-3 py-2 text-[12px]">
                <span className="font-mono">{tool}</span>
                <span className={`badge ${available ? 'badge-success' : 'badge-neutral'}`}>{available ? 'available' : 'missing'}</span>
              </div>
            ))}
          </div>
          <DataNote>Missing tools are reported as skipped by scans. Docker, Terraform and kubectl are only needed for the optional deployment paths.</DataNote>
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card title="Log retention" subtitle="Applies to stored application logs">
          {isAdmin ? (
            <form onSubmit={saveRetention} className="flex flex-wrap items-end gap-2">
              <Field label="Retention window (days)">
                <input type="number" min={1} max={365} className="input w-36" placeholder={String(info.log_retention_days)} value={retention} onChange={(event) => setRetention(event.target.value === '' ? '' : Number(event.target.value))} />
              </Field>
              <button type="submit" className="btn btn-primary" disabled={savingRetention}>
                {savingRetention && <Spinner size={12} />} Save
              </button>
              <button type="button" className="btn btn-secondary" onClick={runCleanup}>
                <Icon name="trash" size={12} /> Run cleanup
              </button>
            </form>
          ) : (
            <p className="text-xs text-slate-500">Administrator role required to change retention.</p>
          )}
          <DataNote>The env value applies until a stored override is saved; cleanup deletes log rows older than the window.</DataNote>
        </Card>

        <Card title="Appearance" subtitle="Preference is stored in this browser">
          <div className="flex gap-2">
            <button type="button" className={`btn ${theme === 'dark' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setTheme('dark')}>
              <Icon name="moon" size={13} /> Dark
            </button>
            <button type="button" className={`btn ${theme === 'light' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setTheme('light')}>
              <Icon name="sun" size={13} /> Light
            </button>
          </div>
          <dl className="mt-3 grid grid-cols-2 gap-2 text-[11.5px]">
            <div><dt className="text-slate-500">Signed in as</dt><dd className="font-medium">{user?.email}</dd></div>
            <div><dt className="text-slate-500">Role</dt><dd className="font-medium">{user?.role}</dd></div>
            <div><dt className="text-slate-500">Last login</dt><dd className="font-medium">{formatDateTime(user?.last_login_at)}</dd></div>
            <div><dt className="text-slate-500">Password rotation</dt><dd className="font-medium">{user?.must_change_password ? 'recommended' : 'up to date'}</dd></div>
          </dl>
        </Card>
      </div>

      <Card
        title="Users"
        subtitle="Role-based access control"
        actions={isAdmin && <button type="button" className="btn btn-primary btn-xs" onClick={() => setUserOpen(true)}><Icon name="plus" size={11} /> Add user</button>}
        bodyClassName=""
      >
        {!isAdmin ? (
          <p className="px-5 py-4 text-xs text-slate-500">Administrator role required to manage users.</p>
        ) : users.loading && !users.data ? (
          <div className="p-4"><Loading rows={3} /></div>
        ) : (
          <div className="overflow-x-auto">
            <table className="table">
              <thead><tr><th>User</th><th>Role</th><th>Status</th><th>Last login</th><th className="text-right">Action</th></tr></thead>
              <tbody>
                {(users.data ?? []).map((item) => (
                  <tr key={item.id}>
                    <td>
                      <p className="text-[12.5px] font-medium">{item.full_name}</p>
                      <p className="text-[10.5px] text-slate-500">{item.email}</p>
                    </td>
                    <td><span className="badge badge-info">{item.role}</span></td>
                    <td><span className={`badge ${item.is_active ? 'badge-success' : 'badge-neutral'}`}>{item.is_active ? 'active' : 'disabled'}</span></td>
                    <td className="text-[11px] text-slate-500">{formatDateTime(item.last_login_at)}</td>
                    <td className="text-right">
                      <button
                        type="button"
                        className="btn btn-secondary btn-xs"
                        disabled={item.id === user?.id}
                        onClick={() => toggleUser(item.id, !item.is_active)}
                      >
                        {item.is_active ? 'Deactivate' : 'Activate'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Modal
        open={pwdOpen}
        onClose={() => setPwdOpen(false)}
        title="Change password"
        subtitle="Passwords are hashed with PBKDF2-HMAC-SHA256."
        footer={
          <>
            <button type="button" className="btn btn-secondary" onClick={() => setPwdOpen(false)}>Cancel</button>
            <button type="submit" form="password-form" className="btn btn-primary" disabled={busy}>Update password</button>
          </>
        }
      >
        <form id="password-form" onSubmit={changePassword} className="space-y-3">
          <Field label="Current password">
            <input type="password" required className="input" value={passwords.current} onChange={(event) => setPasswords({ ...passwords, current: event.target.value })} />
          </Field>
          <Field label="New password" hint="Minimum 8 characters.">
            <input type="password" required minLength={8} className="input" value={passwords.next} onChange={(event) => setPasswords({ ...passwords, next: event.target.value })} />
          </Field>
          <Field label="Confirm new password">
            <input type="password" required minLength={8} className="input" value={passwords.confirm} onChange={(event) => setPasswords({ ...passwords, confirm: event.target.value })} />
          </Field>
        </form>
      </Modal>

      <Modal
        open={userOpen}
        onClose={() => setUserOpen(false)}
        title="Add user"
        subtitle="The new account must change its password at first login."
        footer={
          <>
            <button type="button" className="btn btn-secondary" onClick={() => setUserOpen(false)}>Cancel</button>
            <button type="submit" form="user-form" className="btn btn-primary" disabled={busy}>Create user</button>
          </>
        }
      >
        <form id="user-form" onSubmit={createUser} className="space-y-3">
          <Field label="Full name">
            <input required className="input" value={newUser.full_name} onChange={(event) => setNewUser({ ...newUser, full_name: event.target.value })} />
          </Field>
          <Field label="Email">
            <input type="email" required className="input" value={newUser.email} onChange={(event) => setNewUser({ ...newUser, email: event.target.value })} />
          </Field>
          <Field label="Temporary password" hint="Minimum 8 characters.">
            <input type="password" required minLength={8} className="input" value={newUser.password} onChange={(event) => setNewUser({ ...newUser, password: event.target.value })} />
          </Field>
          <Field label="Role">
            <select className="input" value={newUser.role} onChange={(event) => setNewUser({ ...newUser, role: event.target.value })}>
              <option value="viewer">viewer — read only</option>
              <option value="analyst">analyst — investigate</option>
              <option value="engineer">engineer — operate</option>
              <option value="admin">admin — full control</option>
            </select>
          </Field>
        </form>
      </Modal>
    </div>
  )
}
