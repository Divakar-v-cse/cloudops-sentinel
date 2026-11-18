import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { logsApi } from '../api/endpoints'
import { useApi } from '../hooks/useApi'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../context/ToastContext'
import { Card, DataNote, EmptyState, ErrorState, Loading, PageHeader, Pagination, SeverityBadge, StatCard } from '../components/ui'
import { Icon, Spinner } from '../components/Icon'
import { errorMessage } from '../api/client'
import { formatDateTime, formatTime, timeAgo, truncate } from '../lib/format'
import type { LogAnalysis } from '../types'

export default function Logs() {
  const [params, setParams] = useSearchParams()
  const { isAdmin } = useAuth()
  const toast = useToast()
  const [query, setQuery] = useState(params.get('q') ?? '')
  const [service, setService] = useState('')
  const [severity, setSeverity] = useState('')
  const [hours, setHours] = useState(24)
  const [page, setPage] = useState(1)
  const [analysis, setAnalysis] = useState<LogAnalysis | null>(null)
  const [analysing, setAnalysing] = useState<string | null>(null)

  useEffect(() => {
    setQuery(params.get('q') ?? '')
    setPage(1)
  }, [params])

  const stats = useApi(() => logsApi.stats(hours), [hours])
  const services = useApi(() => logsApi.services(), [])
  const groups = useApi(() => logsApi.groups({ hours, service: service || undefined }), [hours, service])
  const results = useApi(
    () => logsApi.search({ query: query || undefined, service: service || undefined, severity: severity || undefined, hours, page, page_size: 25 }),
    [query, service, severity, hours, page],
  )

  async function analyse(group: { fingerprint: string; service: string }) {
    setAnalysing(group.fingerprint)
    setAnalysis(null)
    try {
      const result = await logsApi.analyze({ fingerprint: group.fingerprint, hours })
      setAnalysis(result)
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setAnalysing(null)
    }
  }

  async function analyseService() {
    setAnalysing('service')
    setAnalysis(null)
    try {
      const result = await logsApi.analyze({ service: service || undefined, hours })
      setAnalysis(result)
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setAnalysing(null)
    }
  }

  async function cleanup() {
    if (!window.confirm('Delete log records older than the retention window?')) return
    try {
      const result = await logsApi.cleanup()
      toast.success(`Purged ${result.deleted} records`)
      stats.reload()
      groups.reload()
      results.reload()
    } catch (err) {
      toast.error(errorMessage(err))
    }
  }

  const bySeverity = stats.data?.by_severity ?? {}

  return (
    <div className="space-y-4">
      <PageHeader
        title="Log intelligence"
        subtitle="Search, group and analyse application logs. Analysis is rule-based by default and never claims a confirmed root cause."
        actions={
          <>
            {isAdmin && (
              <button type="button" className="btn btn-secondary" onClick={cleanup}>
                <Icon name="trash" size={13} /> Retention cleanup
              </button>
            )}
            <button type="button" className="btn btn-secondary" onClick={() => { stats.reload(); groups.reload(); results.reload(); }}>
              <Icon name="refresh" size={13} /> Reload
            </button>
          </>
        }
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-5">
        <StatCard label={`Events (${hours}h)`} value={stats.data?.total ?? 0} icon="file" tone="info" />
        <StatCard label="Errors" value={(bySeverity.error ?? 0) + (bySeverity.critical ?? 0)} hint={`${bySeverity.critical ?? 0} critical`} icon="alert" tone="critical" />
        <StatCard label="Warnings" value={bySeverity.warning ?? 0} icon="alert" tone="warning" />
        <StatCard label="Error groups" value={groups.data?.length ?? 0} hint="Deduplicated by message fingerprint" icon="list" tone="info" />
        <StatCard
          label="Top service"
          value={stats.data?.top_services[0]?.service ?? '—'}
          hint={stats.data?.top_services[0] ? `${stats.data.top_services[0].count} events` : 'No events'}
          icon="server"
          tone="default"
        />
      </div>

      <Card bodyClassName="">
        <div className="flex flex-wrap items-end gap-2 px-4 py-3">
          <div className="min-w-[220px] flex-1">
            <label className="label" htmlFor="log-query">Search</label>
            <div className="relative">
              <span className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400"><Icon name="search" size={14} /></span>
              <input
                id="log-query"
                className="input pl-8"
                placeholder="Message text or trace ID"
                value={query}
                onChange={(event) => {
                  setQuery(event.target.value)
                  setPage(1)
                  if (event.target.value) setParams({ q: event.target.value })
                  else setParams({})
                }}
              />
            </div>
          </div>
          <div>
            <label className="label" htmlFor="log-service">Service</label>
            <select id="log-service" className="input w-44" value={service} onChange={(event) => { setService(event.target.value); setPage(1) }}>
              <option value="">All services</option>
              {(services.data ?? []).map((item) => (
                <option key={item.service} value={item.service}>{item.service}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="log-severity">Severity</label>
            <select id="log-severity" className="input w-32" value={severity} onChange={(event) => { setSeverity(event.target.value); setPage(1) }}>
              <option value="">All</option>
              <option value="critical">critical</option>
              <option value="error">error</option>
              <option value="warning">warning</option>
              <option value="info">info</option>
            </select>
          </div>
          <div>
            <label className="label" htmlFor="log-hours">Window</label>
            <select id="log-hours" className="input w-28" value={hours} onChange={(event) => { setHours(Number(event.target.value)); setPage(1) }}>
              <option value={1}>1 hour</option>
              <option value={6}>6 hours</option>
              <option value={24}>24 hours</option>
              <option value={168}>7 days</option>
              <option value={720}>30 days</option>
            </select>
          </div>
          <button type="button" className="btn btn-primary" onClick={() => { results.reload(); groups.reload(); }}>Apply</button>
        </div>
      </Card>

      <div className="grid gap-4 xl:grid-cols-5">
        <Card
          title="Error groups"
          subtitle={`Grouped by fingerprint · last ${hours}h`}
          className="xl:col-span-2"
          bodyClassName="divide-y"
          actions={<button type="button" className="btn btn-ghost btn-xs" onClick={analyseService} disabled={analysing !== null}>{analysing === 'service' ? <Spinner size={12} /> : <Icon name="activity" size={12} />} Analyse service</button>}
        >
          {groups.loading && !groups.data ? (
            <div className="p-4"><Loading rows={5} /></div>
          ) : (groups.data ?? []).length === 0 ? (
            <EmptyState title="No error groups" description="No warning, error or critical events in this window." icon="check" />
          ) : (
            <div className="max-h-[420px] overflow-y-auto">
              {groups.data!.map((group) => (
                <div key={group.fingerprint} className="px-5 py-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5">
                        <SeverityBadge value={group.severity} />
                        <span className="text-[11px] font-medium text-slate-600 dark:text-slate-300">{group.service}</span>
                      </div>
                      <p className="mt-1 text-[12px] leading-snug text-slate-700 dark:text-slate-200">{truncate(group.sample_message, 110)}</p>
                      <p className="mt-1 text-[10.5px] text-slate-500">
                        {group.count} occurrences · {group.affected_traces} traces · last {timeAgo(group.last_seen)}
                      </p>
                    </div>
                    <button type="button" className="btn btn-secondary btn-xs shrink-0" onClick={() => analyse(group)} disabled={analysing !== null}>
                      {analysing === group.fingerprint ? <Spinner size={12} /> : 'Analyse'}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card
          title="Analysis"
          subtitle={analysis ? `${analysis.source === 'ai' ? 'LLM provider' : 'Deterministic rules'} · ${analysis.log_count ?? 0} lines` : 'Select an error group to analyse'}
          className="xl:col-span-3"
          actions={analysis && <span className={`badge ${analysis.source === 'ai' ? 'badge-info' : 'badge-neutral'}`}>{analysis.source}</span>}
        >
          {analysing ? (
            <div className="flex items-center gap-2 py-8 text-sm text-slate-500"><Spinner size={16} /> Analysing log patterns…</div>
          ) : !analysis ? (
            <EmptyState title="No analysis yet" description="Choose an error group and run analysis to see hypotheses, commands and next steps." icon="activity" />
          ) : (
            <div className="space-y-4">
              <div>
                <div className="flex items-center gap-2">
                  <p className="text-[12.5px] font-semibold text-slate-800 dark:text-slate-100">Summary</p>
                  <span className={`badge ${analysis.confidence === 'high' ? 'badge-success' : analysis.confidence === 'medium' ? 'badge-medium' : 'badge-neutral'}`}>{analysis.confidence} confidence</span>
                </div>
                <p className="mt-1 text-[12.5px] leading-relaxed text-slate-700 dark:text-slate-200">{analysis.summary}</p>
              </div>

              {analysis.hypotheses.length > 0 && (
                <div>
                  <p className="text-[12.5px] font-semibold text-slate-800 dark:text-slate-100">Hypotheses (unconfirmed)</p>
                  <ul className="mt-1.5 space-y-2">
                    {analysis.hypotheses.map((hypothesis) => (
                      <li key={hypothesis.id} className="rounded-lg border px-3 py-2">
                        <p className="text-[12px] font-medium text-slate-700 dark:text-slate-200">{hypothesis.summary}</p>
                        {hypothesis.evidence && <p className="mt-0.5 font-mono text-[10.5px] text-slate-500">{truncate(hypothesis.evidence, 160)}</p>}
                        {hypothesis.causes.length > 0 && (
                          <ul className="mt-1 list-inside list-disc text-[11.5px] text-slate-600 dark:text-slate-300">
                            {hypothesis.causes.map((cause) => <li key={cause}>{cause}</li>)}
                          </ul>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {analysis.debug_commands.length > 0 && (
                <div>
                  <p className="text-[12.5px] font-semibold text-slate-800 dark:text-slate-100">Suggested debugging commands</p>
                  <pre className="code-block mt-1">{analysis.debug_commands.join('\n')}</pre>
                  <p className="mt-1 text-[10.5px] text-slate-500">Review before running. Sentinel never executes these commands.</p>
                </div>
              )}

              <div>
                <p className="text-[12.5px] font-semibold text-slate-800 dark:text-slate-100">Next steps</p>
                <ol className="mt-1 list-inside list-decimal space-y-0.5 text-[11.5px] text-slate-600 dark:text-slate-300">
                  {analysis.next_steps.map((step) => <li key={step}>{step}</li>)}
                </ol>
              </div>

              {analysis.related_incidents.length > 0 && (
                <div>
                  <p className="text-[12.5px] font-semibold text-slate-800 dark:text-slate-100">Related open incidents</p>
                  <ul className="mt-1 space-y-1 text-[11.5px]">
                    {analysis.related_incidents.map((incident) => (
                      <li key={incident.id} className="flex items-center gap-2">
                        <SeverityBadge value={incident.severity} />
                        <span className="font-mono text-[10.5px] text-slate-500">{incident.incident_number}</span>
                        <span>{incident.title}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <DataNote>{analysis.disclaimer}</DataNote>
            </div>
          )}
        </Card>
      </div>

      <Card title="Log search results" subtitle="Newest first" bodyClassName="">
        {results.loading && !results.data ? (
          <div className="p-4"><Loading rows={6} /></div>
        ) : results.error ? (
          <div className="p-4"><ErrorState message={results.error} onRetry={results.reload} /></div>
        ) : results.data?.items.length === 0 ? (
          <EmptyState title="No log records match" description="Adjust the query, service or time window." icon="file" />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="table">
                <thead>
                  <tr><th>Time</th><th>Service</th><th>Severity</th><th>Message</th><th>Trace</th></tr>
                </thead>
                <tbody>
                  {results.data!.items.map((log) => (
                    <tr key={log.id}>
                      <td className="whitespace-nowrap text-[11px] text-slate-500" title={formatDateTime(log.timestamp)}>{formatTime(log.timestamp)}</td>
                      <td className="whitespace-nowrap text-[11.5px] font-medium">{log.service}</td>
                      <td><SeverityBadge value={log.severity} /></td>
                      <td className="max-w-[560px] text-[12px]"><span className="line-clamp-2" title={log.message}>{log.message}</span></td>
                      <td className="font-mono text-[10px] text-slate-500">{log.trace_id ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="px-4 pb-3">
              <Pagination page={results.data?.page ?? 1} pages={results.data?.pages ?? 1} total={results.data?.total ?? 0} onPage={setPage} />
            </div>
          </>
        )}
      </Card>

      <DataNote>
        Ingestion API: <span className="font-mono">POST /api/v1/logs</span> accepts batches of up to 500 records. Severity is
        derived from the level plus message content (for example OOMKilled is escalated to critical). The analysis endpoint uses a
        configured LLM only when AI_PROVIDER and AI_API_KEY are set; otherwise the deterministic rule engine answers.
      </DataNote>
    </div>
  )
}
