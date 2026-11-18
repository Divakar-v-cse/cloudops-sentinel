import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { monitoringApi } from '../api/endpoints'
import { useApi } from '../hooks/useApi'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../context/ToastContext'
import { Card, DataNote, EmptyState, ErrorState, Field, HealthBadge, Loading, PageHeader, SeverityBadge, SourceBadge, StatCard, UsageBar } from '../components/ui'
import { Icon } from '../components/Icon'
import { errorMessage } from '../api/client'
import { formatNumber, formatPercent, timeAgo } from '../lib/format'
import type { Threshold } from '../types'

type SortKey = 'name' | 'cpu' | 'memory' | 'disk'

export default function Monitoring() {
  const { isAdmin, canOperate } = useAuth()
  const toast = useToast()
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [sortKey, setSortKey] = useState<SortKey>('cpu')
  const [sortDesc, setSortDesc] = useState(true)
  const [edits, setEdits] = useState<Record<string, { warning: number; critical: number; enabled: boolean }>>({})
  const [savingMetric, setSavingMetric] = useState<string | null>(null)
  const [spike, setSpike] = useState({ instance_id: '', metric: 'cpu_percent', value: 97, minutes: 3 })

  const poll = autoRefresh ? 20_000 : undefined
  const summary = useApi(() => monitoringApi.summary(), [], { pollMs: poll })
  const alerts = useApi(() => monitoringApi.alerts(25), [], { pollMs: poll })
  const fleet = useApi(() => monitoringApi.fleet(), [], { pollMs: poll })

  const sorted = useMemo(() => {
    const rows = [...(fleet.data ?? [])]
    rows.sort((a, b) => {
      if (sortKey === 'name') return a.instance.name.localeCompare(b.instance.name) * (sortDesc ? -1 : 1)
      const pick = (row: typeof a) =>
        sortKey === 'cpu' ? row.cpu_percent ?? -1 : sortKey === 'memory' ? row.memory_percent ?? -1 : row.disk_percent ?? -1
      return (pick(a) - pick(b)) * (sortDesc ? -1 : 1)
    })
    return rows
  }, [fleet.data, sortKey, sortDesc])

  const simulatedInstances = (fleet.data ?? []).filter((row) => row.instance.source === 'simulated')

  function thresholdValue(threshold: Threshold) {
    return edits[threshold.metric] ?? { warning: threshold.warning, critical: threshold.critical, enabled: threshold.enabled }
  }

  async function saveThreshold(threshold: Threshold) {
    const value = thresholdValue(threshold)
    setSavingMetric(threshold.metric)
    try {
      await monitoringApi.updateThreshold(threshold.metric, value)
      toast.success(`${threshold.display_name} threshold updated`)
      summary.reload()
      setEdits((current) => {
        const next = { ...current }
        delete next[threshold.metric]
        return next
      })
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setSavingMetric(null)
    }
  }

  async function collect() {
    try {
      const result = await monitoringApi.collect()
      toast.success(`Collected ${result.local_samples} local and ${result.simulated_samples} simulated samples`)
      if (result.errors?.length) toast.error(result.errors.join('; '))
      summary.reload()
      alerts.reload()
      fleet.reload()
    } catch (err) {
      toast.error(errorMessage(err))
    }
  }

  async function injectSpike(event: React.FormEvent) {
    event.preventDefault()
    if (!spike.instance_id) {
      toast.error('Select a simulated instance first')
      return
    }
    try {
      const response = await monitoringApi.spike({ ...spike, instance_id: Number(spike.instance_id) })
      toast.success(response.message)
      await monitoringApi.collect()
      alerts.reload()
      fleet.reload()
      summary.reload()
    } catch (err) {
      toast.error(errorMessage(err))
    }
  }

  function toggleSort(key: SortKey) {
    if (sortKey === key) setSortDesc((value) => !value)
    else {
      setSortKey(key)
      setSortDesc(true)
    }
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Monitoring"
        subtitle="Telemetry collection, health classification and threshold alerting for the whole fleet."
        badge={
          <span className={`badge ${autoRefresh ? 'badge-success' : 'badge-neutral'}`}>
            <Icon name="clock" size={11} /> {autoRefresh ? 'auto-refresh 20s' : 'paused'}
          </span>
        }
        actions={
          <>
            <label className="flex items-center gap-2 text-[11px] text-slate-500">
              <input type="checkbox" className="h-3.5 w-3.5" checked={autoRefresh} onChange={(event) => setAutoRefresh(event.target.checked)} />
              Live
            </label>
            <button type="button" className="btn btn-secondary" onClick={collect} disabled={!canOperate}>
              <Icon name="refresh" size={13} /> Collect now
            </button>
            <button type="button" className="btn btn-secondary" onClick={() => { summary.reload(); alerts.reload(); fleet.reload() }}>
              <Icon name="activity" size={13} /> Reload
            </button>
          </>
        }
      />

      {summary.loading && !summary.data ? (
        <Loading rows={5} />
      ) : summary.error ? (
        <ErrorState message={summary.error} onRetry={summary.reload} />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
            <StatCard label="Fleet size" value={summary.data?.instances.total ?? 0} hint={`${summary.data?.instances.running ?? 0} running`} icon="server" tone="info" />
            <StatCard label="Healthy" value={summary.data?.instances.by_health.healthy ?? 0} icon="check" tone="success" />
            <StatCard label="Warning" value={summary.data?.instances.by_health.warning ?? 0} icon="alert" tone="warning" />
            <StatCard label="Critical" value={summary.data?.instances.by_health.critical ?? 0} icon="alert" tone="critical" />
            <StatCard label="Avg CPU" value={formatPercent(summary.data?.utilisation.cpu ?? null)} icon="activity" tone="info" />
            <StatCard label="Avg memory" value={formatPercent(summary.data?.utilisation.memory ?? null)} icon="database" tone="info" />
          </div>

          <div className="grid gap-4 xl:grid-cols-3">
            <Card
              title="Fleet utilisation"
              subtitle="Latest sample per instance, sortable"
              className="xl:col-span-2"
              bodyClassName=""
              actions={
                <Link to="/instances" className="btn btn-ghost btn-xs">
                  Inventory <Icon name="chevron" size={11} />
                </Link>
              }
              footer={`${summary.data?.metric_samples ?? 0} stored samples · retention ${summary.data?.retention_hours ?? 0}h · interval ${summary.data?.interval_seconds ?? 0}s`}
            >
              {fleet.loading && !fleet.data ? (
                <div className="p-4"><Loading rows={6} /></div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>
                          <button type="button" className="uppercase" onClick={() => toggleSort('name')}>Instance</button>
                        </th>
                        <th>Health</th>
                        <th>
                          <button type="button" className="uppercase" onClick={() => toggleSort('cpu')}>CPU</button>
                        </th>
                        <th>
                          <button type="button" className="uppercase" onClick={() => toggleSort('memory')}>Memory</button>
                        </th>
                        <th>
                          <button type="button" className="uppercase" onClick={() => toggleSort('disk')}>Disk</button>
                        </th>
                        <th>Last sample</th>
                      </tr>
                    </thead>
                    <tbody>
                      {sorted.map((row) => (
                        <tr key={row.instance.id}>
                          <td>
                            <Link to={`/instances/${row.instance.id}`} className="font-medium text-brand-600 hover:underline dark:text-brand-400">
                              {row.instance.name}
                            </Link>
                            <div className="mt-0.5 flex items-center gap-1.5">
                              <SourceBadge source={row.instance.source} />
                              <span className="text-[10.5px] text-slate-400">{row.instance.instance_type}</span>
                            </div>
                          </td>
                          <td><HealthBadge value={row.instance.health_status} /></td>
                          <td><UsageBar value={row.cpu_percent} /></td>
                          <td><UsageBar value={row.memory_percent} /></td>
                          <td><UsageBar value={row.disk_percent} /></td>
                          <td className="whitespace-nowrap text-[11px] text-slate-500">{timeAgo(row.timestamp)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>

            <Card title="Active alerts" subtitle="Threshold breaches in the latest sample" bodyClassName="divide-y" footer={`${alerts.data?.length ?? 0} active`}>
              {alerts.loading && !alerts.data ? (
                <div className="p-3"><Loading rows={4} /></div>
              ) : (alerts.data ?? []).length === 0 ? (
                <EmptyState title="No active alerts" description="All instances are inside their thresholds." icon="check" />
              ) : (
                alerts.data!.slice(0, 10).map((alert) => (
                  <div key={`${alert.instance_id}-${alert.metric}`} className="px-5 py-2.5">
                    <div className="flex items-center justify-between gap-2">
                      <Link to={`/instances/${alert.instance_id}`} className="truncate text-[12.5px] font-medium text-slate-800 hover:text-brand-600 dark:text-slate-100">
                        {alert.instance_name}
                      </Link>
                      <SeverityBadge value={alert.level} />
                    </div>
                    <p className="mt-0.5 text-[11px] text-slate-500">
                      {alert.metric.replace('_percent', '').replace('_', ' ')} at {formatNumber(alert.value)} (limit {formatNumber(alert.threshold)})
                    </p>
                  </div>
                ))
              )}
            </Card>
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            <Card
              title="Alert thresholds"
              subtitle={isAdmin ? 'Warning and critical limits applied by the monitoring engine.' : 'Read-only: an administrator can edit thresholds.'}
              bodyClassName=""
            >
              <div className="overflow-x-auto">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Signal</th>
                      <th>Warning</th>
                      <th>Critical</th>
                      <th>Enabled</th>
                      <th className="text-right">Save</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(summary.data?.thresholds ?? []).map((threshold) => {
                      const value = thresholdValue(threshold)
                      const dirty = Boolean(edits[threshold.metric])
                      return (
                        <tr key={threshold.metric}>
                          <td>
                            <p className="text-[12.5px] font-medium">{threshold.display_name}</p>
                            <p className="text-[10.5px] text-slate-500">{threshold.unit} · {threshold.metric}</p>
                          </td>
                          <td>
                            <input
                              type="number"
                              className="input w-24 py-1 text-xs"
                              value={value.warning}
                              disabled={!isAdmin}
                              onChange={(event) => setEdits({ ...edits, [threshold.metric]: { ...value, warning: Number(event.target.value) } })}
                            />
                          </td>
                          <td>
                            <input
                              type="number"
                              className="input w-24 py-1 text-xs"
                              value={value.critical}
                              disabled={!isAdmin}
                              onChange={(event) => setEdits({ ...edits, [threshold.metric]: { ...value, critical: Number(event.target.value) } })}
                            />
                          </td>
                          <td>
                            <input
                              type="checkbox"
                              className="h-3.5 w-3.5"
                              checked={value.enabled}
                              disabled={!isAdmin}
                              onChange={(event) => setEdits({ ...edits, [threshold.metric]: { ...value, enabled: event.target.checked } })}
                            />
                          </td>
                          <td className="text-right">
                            <button
                              type="button"
                              className="btn btn-secondary btn-xs"
                              disabled={!isAdmin || !dirty || savingMetric === threshold.metric}
                              onClick={() => saveThreshold(threshold)}
                            >
                              {savingMetric === threshold.metric ? 'Saving…' : 'Save'}
                            </button>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </Card>

            <div className="space-y-4">
              <Card title="Simulate a threshold breach" subtitle="Injects a synthetic spike so you can verify alerting end to end.">
                {!canOperate ? (
                  <p className="text-xs text-slate-500">Engineering or admin role required.</p>
                ) : (
                  <form onSubmit={injectSpike} className="space-y-3">
                    <div className="grid gap-3 sm:grid-cols-2">
                      <Field label="Simulated instance">
                        <select className="input" value={spike.instance_id} onChange={(event) => setSpike({ ...spike, instance_id: event.target.value })}>
                          <option value="">Select instance…</option>
                          {simulatedInstances.map((row) => (
                            <option key={row.instance.id} value={row.instance.id}>{row.instance.name}</option>
                          ))}
                        </select>
                      </Field>
                      <Field label="Signal">
                        <select className="input" value={spike.metric} onChange={(event) => setSpike({ ...spike, metric: event.target.value })}>
                          <option value="cpu_percent">CPU</option>
                          <option value="memory_percent">Memory</option>
                          <option value="disk_percent">Disk</option>
                        </select>
                      </Field>
                      <Field label="Value (%)">
                        <input type="number" min={1} max={100} className="input" value={spike.value} onChange={(event) => setSpike({ ...spike, value: Number(event.target.value) })} />
                      </Field>
                      <Field label="Duration (minutes)">
                        <input type="number" min={1} max={60} className="input" value={spike.minutes} onChange={(event) => setSpike({ ...spike, minutes: Number(event.target.value) })} />
                      </Field>
                    </div>
                    <button type="submit" className="btn btn-primary">
                      <Icon name="activity" size={13} /> Inject spike and collect
                    </button>
                  </form>
                )}
              </Card>

              <Card title="Collection configuration" subtitle="Effective runtime settings for this process">
                <dl className="grid grid-cols-2 gap-3 text-[12px]">
                  <div><dt className="text-slate-500">Interval</dt><dd className="font-medium">{summary.data?.interval_seconds}s</dd></div>
                  <div><dt className="text-slate-500">Retention</dt><dd className="font-medium">{summary.data?.retention_hours}h</dd></div>
                  <div><dt className="text-slate-500">Scheduler</dt><dd className="font-medium">{summary.data?.scheduler_running ? 'running' : 'disabled'}</dd></div>
                  <div><dt className="text-slate-500">Local collector</dt><dd className="font-medium">{summary.data?.local_collector ? 'enabled' : 'off'}</dd></div>
                </dl>
                <DataNote>
                  Data sources: {(summary.data?.data_sources ?? []).join(', ')}. Interval and retention are environment
                  settings; change MONITORING_INTERVAL_SECONDS / MONITORING_HISTORY_RETENTION_HOURS and restart.
                </DataNote>
              </Card>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
