import { useState } from 'react'
import { incidentsApi } from '../api/endpoints'
import { useApi } from '../hooks/useApi'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../context/ToastContext'
import { Card, DataNote, EmptyState, ErrorState, Field, Loading, Modal, PageHeader, Pagination, SeverityBadge, StatCard } from '../components/ui'
import { Icon, Spinner } from '../components/Icon'
import { errorMessage } from '../api/client'
import { formatDateTime, formatDuration, timeAgo } from '../lib/format'
import type { Incident } from '../types'

const TRANSITIONS: Record<string, string[]> = {
  detected: ['acknowledged', 'investigating', 'resolved'],
  acknowledged: ['investigating', 'resolved'],
  investigating: ['resolved'],
  resolved: ['closed'],
  closed: [],
}

const STATUS_STYLES: Record<string, string> = {
  detected: 'badge badge-critical',
  acknowledged: 'badge badge-medium',
  investigating: 'badge badge-info',
  resolved: 'badge badge-success',
  closed: 'badge badge-neutral',
}

export default function Incidents() {
  const { canOperate } = useAuth()
  const toast = useToast()
  const [status, setStatus] = useState('')
  const [severity, setSeverity] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<number | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [form, setForm] = useState({ title: '', description: '', severity: 'medium', service: '', assigned_to: '' })
  const [saving, setSaving] = useState(false)
  const [note, setNote] = useState('')
  const [resolution, setResolution] = useState('')
  const [pendingStatus, setPendingStatus] = useState<string | null>(null)
  const [working, setWorking] = useState(false)

  const stats = useApi(() => incidentsApi.stats(), [])
  const list = useApi(
    () => incidentsApi.list({ page, page_size: 15, status: status || undefined, severity: severity || undefined, search: search || undefined }),
    [page, status, severity, search],
  )
  const detail = useApi(() => incidentsApi.get(selected as number), [selected], { enabled: selected !== null })

  async function createIncident(event: React.FormEvent) {
    event.preventDefault()
    setSaving(true)
    try {
      const created = await incidentsApi.create({
        title: form.title,
        description: form.description,
        severity: form.severity,
        service: form.service || undefined,
        assigned_to: form.assigned_to || undefined,
        detected_by: 'manual',
      })
      toast.success(`Incident ${created.incident_number} created`)
      setCreateOpen(false)
      setForm({ title: '', description: '', severity: 'medium', service: '', assigned_to: '' })
      list.reload()
      stats.reload()
      setSelected(created.id)
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  async function transition(next: string) {
    if (!selected) return
    if (next === 'resolved' && !resolution.trim()) {
      setPendingStatus('resolved')
      return
    }
    setWorking(true)
    try {
      await incidentsApi.changeStatus(selected, {
        status: next,
        note: note.trim() || undefined,
        resolution_summary: next === 'resolved' ? resolution.trim() : undefined,
      })
      toast.success(`Incident moved to ${next}`)
      setNote('')
      setResolution('')
      setPendingStatus(null)
      detail.reload()
      list.reload()
      stats.reload()
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setWorking(false)
    }
  }

  async function addNote(event: React.FormEvent) {
    event.preventDefault()
    if (!selected || !note.trim()) return
    setWorking(true)
    try {
      await incidentsApi.addNote(selected, note.trim())
      setNote('')
      detail.reload()
      toast.success('Investigation note added')
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setWorking(false)
    }
  }

  const incident = detail.data

  return (
    <div className="space-y-4">
      <PageHeader
        title="Incident management"
        subtitle="DETECTED → ACKNOWLEDGED → INVESTIGATING → RESOLVED → CLOSED, with a full timeline and audit trail."
        actions={
          canOperate && (
            <button type="button" className="btn btn-primary" onClick={() => setCreateOpen(true)}>
              <Icon name="plus" size={13} /> New incident
            </button>
          )
        }
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <StatCard label="Open" value={stats.data?.open ?? 0} icon="alert" tone={stats.data?.critical_open ? 'critical' : 'warning'} />
        <StatCard label="Critical open" value={stats.data?.critical_open ?? 0} icon="alert" tone="critical" />
        <StatCard label="Opened (7d)" value={stats.data?.last_7_days ?? 0} icon="clock" tone="info" />
        <StatCard label="MTTA" value={stats.data?.mtta_minutes !== null && stats.data?.mtta_minutes !== undefined ? formatDuration(stats.data.mtta_minutes) : '—'} hint="Mean time to acknowledge" icon="clock" tone="default" />
        <StatCard label="MTTR" value={stats.data?.mttr_minutes !== null && stats.data?.mttr_minutes !== undefined ? formatDuration(stats.data.mttr_minutes) : '—'} hint="Mean time to resolve" icon="activity" tone="success" />
        <StatCard label="Total" value={stats.data?.total ?? 0} hint={`Risk score ${stats.data?.risk_score ?? 0}`} icon="list" tone="default" />
      </div>

      <Card bodyClassName="">
        <div className="flex flex-wrap items-end gap-2 border-b px-4 py-3">
          <div className="min-w-[200px] flex-1">
            <label className="label" htmlFor="incident-search">Search</label>
            <input id="incident-search" className="input" placeholder="Title, number or description" value={search} onChange={(event) => { setSearch(event.target.value); setPage(1) }} />
          </div>
          <div>
            <label className="label" htmlFor="incident-status">Status</label>
            <select id="incident-status" className="input w-40" value={status} onChange={(event) => { setStatus(event.target.value); setPage(1) }}>
              <option value="">All</option>
              {Object.keys(TRANSITIONS).map((value) => <option key={value} value={value}>{value}</option>)}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="incident-severity">Severity</label>
            <select id="incident-severity" className="input w-32" value={severity} onChange={(event) => { setSeverity(event.target.value); setPage(1) }}>
              <option value="">All</option>
              <option value="critical">critical</option>
              <option value="high">high</option>
              <option value="medium">medium</option>
              <option value="low">low</option>
            </select>
          </div>
        </div>

        {list.loading && !list.data ? (
          <div className="p-4"><Loading rows={6} /></div>
        ) : list.error ? (
          <div className="p-4"><ErrorState message={list.error} onRetry={list.reload} /></div>
        ) : list.data?.items.length === 0 ? (
          <EmptyState title="No incidents match" description="Adjust filters, or open an incident manually." icon="alert" />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="table">
                <thead>
                  <tr><th>Incident</th><th>Severity</th><th>Status</th><th>Service</th><th>Assignee</th><th>Opened</th><th className="text-right">View</th></tr>
                </thead>
                <tbody>
                  {list.data!.items.map((item: Incident) => (
                    <tr key={item.id} className="cursor-pointer" onClick={() => setSelected(item.id)}>
                      <td>
                        <p className="text-[12.5px] font-medium text-slate-800 dark:text-slate-100">{item.title}</p>
                        <p className="font-mono text-[10.5px] text-slate-500">{item.incident_number}</p>
                      </td>
                      <td><SeverityBadge value={item.severity} /></td>
                      <td><span className={STATUS_STYLES[item.status] ?? 'badge badge-neutral'}>{item.status}</span></td>
                      <td className="text-[11.5px]">{item.service ?? '—'}</td>
                      <td className="text-[11.5px]">{item.assigned_to ?? 'unassigned'}</td>
                      <td className="whitespace-nowrap text-[11px] text-slate-500">{timeAgo(item.created_at)}</td>
                      <td className="text-right">
                        <button type="button" className="btn btn-ghost btn-xs" onClick={(event) => { event.stopPropagation(); setSelected(item.id) }}>
                          <Icon name="eye" size={13} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="px-4 pb-3">
              <Pagination page={list.data?.page ?? 1} pages={list.data?.pages ?? 1} total={list.data?.total ?? 0} onPage={setPage} />
            </div>
          </>
        )}
      </Card>

      <DataNote>
        Incidents are opened automatically by monitoring (deduplicated per instance and signal) and by operators. Every status
        change requires a valid transition, is recorded on the timeline and written to the audit log.
      </DataNote>

      {/* detail */}
      <Modal
        open={selected !== null}
        onClose={() => { setSelected(null); setPendingStatus(null); setResolution(''); setNote('') }}
        title={incident ? `${incident.incident_number} · ${incident.title}` : 'Incident'}
        subtitle={incident ? `${incident.service ?? 'unassigned service'} · opened ${formatDateTime(incident.created_at)} · ${formatDuration(incident.duration_minutes)}` : ''}
        wide
        footer={
          incident && (
            <div className="flex flex-wrap items-center justify-end gap-2">
              {TRANSITIONS[incident.status].length === 0 && <span className="text-[11px] text-slate-500">Closed incidents can be reopened from the API.</span>}
              {TRANSITIONS[incident.status].map((next) => (
                <button
                  key={next}
                  type="button"
                  className={`btn ${next === 'resolved' ? 'btn-primary' : 'btn-secondary'} btn-xs`}
                  disabled={working || !canOperate}
                  onClick={() => transition(next)}
                >
                  {working && <Spinner size={11} />} {next === 'acknowledged' ? 'Acknowledge' : next === 'investigating' ? 'Start investigation' : next === 'resolved' ? 'Resolve' : 'Close'}
                </button>
              ))}
            </div>
          )
        }
      >
        {detail.loading && !incident ? (
          <Loading rows={5} />
        ) : detail.error ? (
          <ErrorState message={detail.error} onRetry={detail.reload} />
        ) : incident ? (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <SeverityBadge value={incident.severity} />
              <span className={STATUS_STYLES[incident.status] ?? 'badge badge-neutral'}>{incident.status}</span>
              <span className="badge badge-neutral">detected by {incident.detected_by}</span>
              <span className="badge badge-neutral">assignee {incident.assigned_to ?? 'unassigned'}</span>
            </div>

            <p className="text-[12.5px] leading-relaxed text-slate-700 dark:text-slate-200">{incident.description || 'No description provided.'}</p>

            {incident.resolution_summary && (
              <div className="rounded-lg border border-emerald-300/50 bg-emerald-50 px-3 py-2 dark:border-emerald-500/30 dark:bg-emerald-950/40">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-emerald-700 dark:text-emerald-300">Resolution</p>
                <p className="mt-1 text-[12px] text-emerald-800 dark:text-emerald-200">{incident.resolution_summary}</p>
              </div>
            )}

            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500">Timeline</p>
                <ol className="space-y-2.5">
                  {incident.notes.map((entry) => (
                    <li key={entry.id} className="relative border-l-2 border-slate-200 pl-3 dark:border-slate-700">
                      <span className="absolute -left-[5px] top-1.5 h-2 w-2 rounded-full bg-brand-500" />
                      <p className="text-[11.5px] text-slate-700 dark:text-slate-200">{entry.note}</p>
                      <p className="text-[10px] text-slate-500">
                        {entry.author} · {formatDateTime(entry.created_at)}
                        {entry.status_change && <span className="ml-1 font-medium">→ {entry.status_change}</span>}
                      </p>
                    </li>
                  ))}
                </ol>
              </div>

              <div className="space-y-3">
                {pendingStatus === 'resolved' && (
                  <div className="rounded-lg border border-brand-300 bg-brand-50 p-3 dark:border-brand-500/40 dark:bg-brand-500/10">
                    <p className="text-[11.5px] font-medium text-brand-800 dark:text-brand-200">Resolution summary required</p>
                    <textarea className="input mt-1.5 h-20" value={resolution} onChange={(event) => setResolution(event.target.value)} placeholder="What fixed it? Include verification steps." />
                    <div className="mt-1.5 flex gap-2">
                      <button type="button" className="btn btn-primary btn-xs" disabled={!resolution.trim() || working} onClick={() => transition('resolved')}>
                        Confirm resolution
                      </button>
                      <button type="button" className="btn btn-secondary btn-xs" onClick={() => setPendingStatus(null)}>Cancel</button>
                    </div>
                  </div>
                )}
                <form onSubmit={addNote}>
                  <Field label="Add investigation note">
                    <textarea className="input h-20" value={note} onChange={(event) => setNote(event.target.value)} placeholder="Findings, commands run, hypotheses…" />
                  </Field>
                  <button type="submit" className="btn btn-secondary btn-xs mt-1.5" disabled={!note.trim() || working || !canOperate}>
                    <Icon name="plus" size={11} /> Add note
                  </button>
                </form>

                <dl className="grid grid-cols-2 gap-2 text-[11px]">
                  <div><dt className="text-slate-500">Acknowledged</dt><dd>{formatDateTime(incident.acknowledged_at)}</dd></div>
                  <div><dt className="text-slate-500">Resolved</dt><dd>{formatDateTime(incident.resolved_at)}</dd></div>
                  <div><dt className="text-slate-500">Closed</dt><dd>{formatDateTime(incident.closed_at)}</dd></div>
                  <div><dt className="text-slate-500">Duration</dt><dd>{formatDuration(incident.duration_minutes)}</dd></div>
                </dl>
              </div>
            </div>
          </div>
        ) : null}
      </Modal>

      {/* create */}
      <Modal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title="Open an incident"
        subtitle="Manual incidents are recorded exactly like automatically detected ones."
        footer={
          <>
            <button type="button" className="btn btn-secondary" onClick={() => setCreateOpen(false)}>Cancel</button>
            <button type="submit" form="incident-form" className="btn btn-primary" disabled={saving}>{saving ? 'Creating…' : 'Create incident'}</button>
          </>
        }
      >
        <form id="incident-form" onSubmit={createIncident} className="space-y-3">
          <Field label="Title">
            <input required minLength={4} className="input" value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} placeholder="Elevated error rate on checkout-api" />
          </Field>
          <Field label="Description">
            <textarea className="input h-24" value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} placeholder="Symptoms, scope and time detected." />
          </Field>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Severity">
              <select className="input" value={form.severity} onChange={(event) => setForm({ ...form, severity: event.target.value })}>
                <option value="critical">critical</option>
                <option value="high">high</option>
                <option value="medium">medium</option>
                <option value="low">low</option>
              </select>
            </Field>
            <Field label="Service">
              <input className="input" value={form.service} onChange={(event) => setForm({ ...form, service: event.target.value })} placeholder="checkout-api" />
            </Field>
          </div>
          <Field label="Assign to (email)" hint="Optional. Leave empty for the unassigned queue.">
            <input className="input" value={form.assigned_to} onChange={(event) => setForm({ ...form, assigned_to: event.target.value })} />
          </Field>
        </form>
      </Modal>
    </div>
  )
}
