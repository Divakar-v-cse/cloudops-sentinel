import { useState } from 'react'
import { platformApi } from '../api/endpoints'
import { useApi } from '../hooks/useApi'
import { Card, DataNote, EmptyState, ErrorState, Loading, PageHeader, Pagination, StatCard } from '../components/ui'
import { Icon } from '../components/Icon'
import { formatDateTime } from '../lib/format'

export default function Audit() {
  const [action, setAction] = useState('')
  const [entity, setEntity] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [expanded, setExpanded] = useState<number | null>(null)

  const facets = useApi(() => platformApi.auditFacets(), [])
  const logs = useApi(
    () => platformApi.audit({ page, page_size: 30, action: action || undefined, entity_type: entity || undefined, search: search || undefined }),
    [page, action, entity, search],
  )

  return (
    <div className="space-y-4">
      <PageHeader
        title="Audit logs"
        subtitle="Append-only record of authentication, configuration, security, incident and remediation activity."
        actions={
          <button type="button" className="btn btn-secondary" onClick={() => { logs.reload(); facets.reload(); }}>
            <Icon name="refresh" size={13} /> Refresh
          </button>
        }
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard label="Audit records" value={facets.data?.total ?? 0} icon="list" tone="info" />
        <StatCard label="Distinct actions" value={facets.data?.actions.length ?? 0} icon="activity" tone="default" />
        <StatCard label="Entity types" value={facets.data?.entity_types.length ?? 0} icon="database" tone="default" />
        <StatCard label="Retention" value="append-only" hint="Entries are never edited or deleted by the application" icon="shield" tone="success" />
      </div>

      <Card title="Most frequent actions" subtitle="Click a chip to filter">
        <div className="flex flex-wrap gap-1.5">
          {(facets.data?.actions ?? []).slice(0, 18).map((item) => (
            <button
              key={item.action}
              type="button"
              onClick={() => { setAction(action === item.action ? '' : item.action); setPage(1) }}
              className={`badge ${action === item.action ? 'badge-info' : 'badge-neutral'} cursor-pointer`}
            >
              {item.action} <span className="opacity-60">{item.count}</span>
            </button>
          ))}
          {(facets.data?.actions ?? []).length === 0 && <span className="text-xs text-slate-500">No audit entries yet.</span>}
        </div>
      </Card>

      <Card bodyClassName="">
        <div className="flex flex-wrap items-end gap-2 border-b px-4 py-3">
          <div className="min-w-[200px] flex-1">
            <label className="label" htmlFor="audit-search">Search</label>
            <input id="audit-search" className="input" placeholder="Action or entity id" value={search} onChange={(event) => { setSearch(event.target.value); setPage(1) }} />
          </div>
          <div>
            <label className="label" htmlFor="audit-action">Action</label>
            <select id="audit-action" className="input w-52" value={action} onChange={(event) => { setAction(event.target.value); setPage(1) }}>
              <option value="">All actions</option>
              {(facets.data?.actions ?? []).map((item) => <option key={item.action} value={item.action}>{item.action}</option>)}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="audit-entity">Entity type</label>
            <select id="audit-entity" className="input w-44" value={entity} onChange={(event) => { setEntity(event.target.value); setPage(1) }}>
              <option value="">All entities</option>
              {(facets.data?.entity_types ?? []).map((item) => <option key={item.entity_type} value={item.entity_type}>{item.entity_type}</option>)}
            </select>
          </div>
        </div>

        {logs.loading && !logs.data ? (
          <div className="p-4"><Loading rows={8} /></div>
        ) : logs.error ? (
          <div className="p-4"><ErrorState message={logs.error} onRetry={logs.reload} /></div>
        ) : logs.data?.items.length === 0 ? (
          <EmptyState title="No audit entries match" description="Clear the filters to see the full trail." icon="list" />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="table">
                <thead>
                  <tr><th>Time</th><th>Actor</th><th>Action</th><th>Entity</th><th>IP</th><th /></tr>
                </thead>
                <tbody>
                  {logs.data!.items.map((entry) => (
                    <tr key={entry.id}>
                      <td className="whitespace-nowrap text-[11px] text-slate-500">{formatDateTime(entry.created_at)}</td>
                      <td className="max-w-[180px] truncate text-[11.5px]">{entry.actor}</td>
                      <td><span className="badge badge-neutral font-mono text-[10px]">{entry.action}</span></td>
                      <td className="text-[11px]">
                        {entry.entity_type}
                        {entry.entity_id && <span className="ml-1 font-mono text-[10px] text-slate-500">#{entry.entity_id}</span>}
                      </td>
                      <td className="font-mono text-[10.5px] text-slate-500">{entry.ip_address ?? '—'}</td>
                      <td className="text-right">
                        <button type="button" className="btn btn-ghost btn-xs" onClick={() => setExpanded(expanded === entry.id ? null : entry.id)}>
                          <Icon name="eye" size={12} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {expanded !== null && (
              <div className="border-t bg-slate-50 px-4 py-3 dark:bg-slate-950/40">
                <p className="mb-1 text-[10.5px] font-semibold uppercase tracking-wide text-slate-500">Entry detail</p>
                <pre className="code-block whitespace-pre-wrap">
                  {JSON.stringify(logs.data!.items.find((item) => item.id === expanded)?.detail ?? {}, null, 2)}
                </pre>
              </div>
            )}
            <div className="px-4 pb-3">
              <Pagination page={logs.data?.page ?? 1} pages={logs.data?.pages ?? 1} total={logs.data?.total ?? 0} onPage={setPage} />
            </div>
          </>
        )}
      </Card>

      <DataNote>
        Audit entries record the acting principal, action, entity and a structured detail payload. They are written for logins,
        scans, threshold changes, incident transitions, remediation approvals and settings updates.
      </DataNote>
    </div>
  )
}
