import { Link, useNavigate } from 'react-router-dom'
import { dashboardApi } from '../api/endpoints'
import { useApi } from '../hooks/useApi'
import { AreaTrend, Donut } from '../components/Charts'
import { Card, DataNote, EmptyState, ErrorState, HealthBadge, Loading, PageHeader, SeverityBadge, SourceBadge, StatCard } from '../components/ui'
import { Icon } from '../components/Icon'
import { formatMoney, formatPercent, formatTime, timeAgo } from '../lib/format'

export default function Overview() {
  const navigate = useNavigate()
  const { data, error, loading, reload, updatedAt } = useApi(() => dashboardApi.overview(), [], { pollMs: 30_000 })

  if (loading && !data) {
    return (
      <div>
        <PageHeader title="Overview" subtitle="Loading platform state…" />
        <Loading rows={6} />
      </div>
    )
  }

  if (error && !data) {
    return (
      <div>
        <PageHeader title="Overview" />
        <ErrorState message={error} onRetry={reload} />
      </div>
    )
  }

  if (!data) return null

  const simulated = data.mode.data_sources.simulated ?? 0
  const localCount = data.mode.data_sources.local ?? 0
  const awsCount = data.mode.data_sources.aws ?? 0

  const healthData = [
    { name: 'Healthy', value: data.instances.by_health.healthy ?? 0, color: '#10b981' },
    { name: 'Warning', value: data.instances.by_health.warning ?? 0, color: '#f59e0b' },
    { name: 'Critical', value: data.instances.by_health.critical ?? 0, color: '#f43f5e' },
    { name: 'Offline', value: (data.instances.by_health.offline ?? 0) + (data.instances.by_health.unknown ?? 0), color: '#64748b' },
  ].filter((item) => item.value > 0)

  const trend = data.trend.map((point) => ({ ...point, label: formatTime(point.bucket) }))

  return (
    <div className="space-y-5">
      <PageHeader
        title="Overview"
        subtitle="Live platform state aggregated from monitoring, security, cost, log and deployment modules."
        badge={
          <span className="badge badge-info">
            <Icon name="clock" size={11} /> {updatedAt ? timeAgo(updatedAt.toISOString()) : 'just now'}
          </span>
        }
        actions={
          <>
            <button type="button" className="btn btn-secondary" onClick={reload} disabled={loading}>
              <Icon name="refresh" size={13} /> Refresh
            </button>
            <Link to="/incidents" className="btn btn-primary">
              <Icon name="alert" size={13} /> Incident queue ({data.incidents.open})
            </Link>
          </>
        }
      />

      <DataNote>
        <span className="font-medium text-slate-600 dark:text-slate-300">Data provenance:</span>{' '}
        {localCount} local host{localCount === 1 ? '' : 's'} measured with psutil, {simulated} simulated instance
        {simulated === 1 ? '' : 's'}, {awsCount} imported from AWS. AWS mode:{' '}
        <span className="font-medium">{data.mode.aws}</span>. Simulated records are labelled everywhere they appear.
      </DataNote>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
        <StatCard label="Total instances" value={data.instances.total} hint={`${data.instances.running} running`} icon="server" tone="info" onClick={() => navigate('/instances')} />
        <StatCard label="Healthy" value={data.instances.by_health.healthy ?? 0} hint="Within all thresholds" icon="check" tone="success" onClick={() => navigate('/monitoring')} />
        <StatCard label="Warning" value={data.instances.by_health.warning ?? 0} hint="Approaching a threshold" icon="alert" tone="warning" onClick={() => navigate('/monitoring')} />
        <StatCard
          label="Critical incidents"
          value={data.incidents.critical}
          hint={`${data.incidents.open} open · ${data.incidents.total} total`}
          icon="alert"
          tone="critical"
          onClick={() => navigate('/incidents')}
        />
        <StatCard label="CPU utilisation" value={formatPercent(data.utilisation.cpu)} hint="Fleet average, latest sample" icon="activity" tone="info" onClick={() => navigate('/monitoring')} />
        <StatCard label="Memory utilisation" value={formatPercent(data.utilisation.memory)} hint="Fleet average, latest sample" icon="database" tone="info" onClick={() => navigate('/monitoring')} />
        <StatCard
          label="Security risk"
          value={data.security.open_findings}
          hint={`${data.security.critical} critical · ${data.security.high} high · score ${data.security.risk_score}`}
          icon="shield"
          tone={data.security.critical > 0 ? 'critical' : 'warning'}
          onClick={() => navigate('/security')}
        />
        <StatCard
          label="Monthly estimated cost"
          value={formatMoney(data.cost.estimated_monthly_usd, data.cost.currency)}
          hint={`${formatPercent(data.cost.budget_used_percent, 0)} of ${formatMoney(data.cost.budget_usd, data.cost.currency)} budget · estimated`}
          icon="dollar"
          tone="info"
          onClick={() => navigate('/costs')}
        />
        <StatCard
          label="Deployment status"
          value={data.deployments.last_status}
          hint={`${data.deployments.last_service ?? '—'} ${data.deployments.last_version ?? ''} · ${data.deployments.success_rate}% success`}
          icon="git"
          tone={data.deployments.last_status === 'success' ? 'success' : data.deployments.last_status === 'failed' ? 'critical' : 'default'}
          onClick={() => navigate('/pipelines')}
        />
        <StatCard
          label="Recent alerts"
          value={data.alerts.length}
          hint={`${data.logs.errors_24h} errors logged in 24h`}
          icon="bell"
          tone={data.alerts.some((alert) => alert.level === 'critical') ? 'critical' : 'warning'}
          onClick={() => navigate('/monitoring')}
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Card
          title="Fleet utilisation"
          subtitle="Average CPU, memory and disk over the last 12 hours"
          className="xl:col-span-2"
          actions={<Link to="/monitoring" className="btn btn-ghost btn-xs">Open monitoring <Icon name="chevron" size={12} /></Link>}
        >
          {trend.length === 0 ? (
            <EmptyState title="No telemetry yet" description="Run a collection cycle from Monitoring to populate history." icon="activity" />
          ) : (
            <AreaTrend
              data={trend}
              xKey="label"
              height={260}
              series={[
                { key: 'cpu', label: 'CPU', color: '#3186fb' },
                { key: 'memory', label: 'Memory', color: '#8b5cf6' },
                { key: 'disk', label: 'Disk', color: '#f59e0b' },
              ]}
            />
          )}
        </Card>

        <Card title="Instance health" subtitle="Current classification across the fleet">
          {healthData.length === 0 ? (
            <EmptyState title="No instances" description="Add a simulated instance or register the local host." icon="server" />
          ) : (
            <>
              <Donut data={healthData} centerLabel="instances" centerValue={String(data.instances.total)} />
              <div className="mt-2 grid grid-cols-2 gap-2 text-[11.5px]">
                {healthData.map((item) => (
                  <span key={item.name} className="flex items-center gap-1.5 text-slate-600 dark:text-slate-300">
                    <span className="h-2 w-2 rounded-full" style={{ backgroundColor: item.color }} /> {item.name}: {item.value}
                  </span>
                ))}
              </div>
            </>
          )}
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card
          title="Active alerts"
          subtitle="Threshold breaches from the latest sample of each instance"
          actions={<Link to="/monitoring" className="btn btn-ghost btn-xs">All alerts</Link>}
          bodyClassName=""
        >
          {data.alerts.length === 0 ? (
            <EmptyState title="No active alerts" description="Every instance is inside its configured thresholds." icon="check" />
          ) : (
            <div className="overflow-x-auto">
              <table className="table">
                <thead>
                  <tr>
                    <th>Instance</th>
                    <th>Signal</th>
                    <th>Value</th>
                    <th>Level</th>
                    <th>Observed</th>
                  </tr>
                </thead>
                <tbody>
                  {data.alerts.slice(0, 6).map((alert) => (
                    <tr key={`${alert.instance_id}-${alert.metric}`}>
                      <td>
                        <Link to={`/instances/${alert.instance_id}`} className="font-medium text-brand-600 hover:underline dark:text-brand-400">
                          {alert.instance_name}
                        </Link>
                        <div className="mt-0.5"><SourceBadge source={alert.source} /></div>
                      </td>
                      <td className="text-xs uppercase tracking-wide text-slate-500">{alert.metric.replace('_percent', '').replace('_', ' ')}</td>
                      <td className="tabular-nums">{alert.value.toFixed(1)}</td>
                      <td><SeverityBadge value={alert.level} /></td>
                      <td className="whitespace-nowrap text-xs text-slate-500">{timeAgo(alert.timestamp)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <Card
          title="Recent incidents"
          subtitle="Newest incidents from the incident manager"
          actions={<Link to="/incidents" className="btn btn-ghost btn-xs">Incident queue</Link>}
          bodyClassName="divide-y"
        >
          {data.recent_incidents.length === 0 ? (
            <EmptyState title="No incidents" description="Nothing has been opened by monitoring or operators." icon="shield" />
          ) : (
            data.recent_incidents.map((incident) => (
              <Link key={incident.id} to="/incidents" className="flex items-start justify-between gap-3 px-5 py-3 transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/40">
                <div className="min-w-0">
                  <p className="truncate text-[13px] font-medium text-slate-800 dark:text-slate-100">{incident.title}</p>
                  <p className="mt-0.5 text-[11px] text-slate-500 dark:text-slate-400">
                    {incident.incident_number} · {incident.service ?? 'unassigned'} · {timeAgo(incident.created_at)}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-1.5">
                  <SeverityBadge value={incident.severity} />
                  <span className="badge badge-neutral">{incident.status}</span>
                </div>
              </Link>
            ))
          )}
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card
          title="Latest security findings"
          subtitle="Open findings ordered by most recently observed"
          actions={<Link to="/security" className="btn btn-ghost btn-xs">All findings</Link>}
          bodyClassName=""
        >
          {data.recent_findings.length === 0 ? (
            <EmptyState title="No open findings" description="Run a security scan to evaluate configuration." icon="shield" />
          ) : (
            <div className="overflow-x-auto">
              <table className="table">
                <thead>
                  <tr>
                    <th>Finding</th>
                    <th>Severity</th>
                    <th>Origin</th>
                  </tr>
                </thead>
                <tbody>
                  {data.recent_findings.map((finding) => (
                    <tr key={finding.id}>
                      <td>
                        <Link to="/security" className="text-[12.5px] font-medium text-slate-800 hover:text-brand-600 dark:text-slate-100">
                          {finding.title}
                        </Link>
                        <p className="mt-0.5 truncate text-[11px] text-slate-500">{finding.resource_name}</p>
                      </td>
                      <td><SeverityBadge value={finding.severity} /></td>
                      <td><SourceBadge source={finding.source_kind} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <Card title="Operational summary" subtitle="Signals that usually need attention first">
          <dl className="grid grid-cols-2 gap-3 text-sm">
            <div className="rounded-lg border p-3">
              <dt className="text-[11px] uppercase tracking-wide text-slate-500">Pending approvals</dt>
              <dd className="mt-1 text-lg font-semibold text-slate-900 dark:text-slate-50">{data.remediation.pending_approvals}</dd>
              <Link to="/remediation" className="text-[11px] text-brand-600 hover:underline dark:text-brand-400">Remediation center →</Link>
            </div>
            <div className="rounded-lg border p-3">
              <dt className="text-[11px] uppercase tracking-wide text-slate-500">Potential savings</dt>
              <dd className="mt-1 text-lg font-semibold text-emerald-600 dark:text-emerald-400">{formatMoney(data.cost.potential_savings_usd)}<span className="text-xs font-normal text-slate-500">/mo</span></dd>
              <Link to="/costs" className="text-[11px] text-brand-600 hover:underline dark:text-brand-400">Cost recommendations →</Link>
            </div>
            <div className="rounded-lg border p-3">
              <dt className="text-[11px] uppercase tracking-wide text-slate-500">Errors (24h)</dt>
              <dd className="mt-1 text-lg font-semibold text-slate-900 dark:text-slate-50">{data.logs.errors_24h}</dd>
              <Link to="/logs" className="text-[11px] text-brand-600 hover:underline dark:text-brand-400">Log intelligence →</Link>
            </div>
            <div className="rounded-lg border p-3">
              <dt className="text-[11px] uppercase tracking-wide text-slate-500">Unread notifications</dt>
              <dd className="mt-1 text-lg font-semibold text-slate-900 dark:text-slate-50">{data.notifications.unread}</dd>
              <Link to="/audit" className="text-[11px] text-brand-600 hover:underline dark:text-brand-400">Audit trail →</Link>
            </div>
          </dl>
        </Card>
      </div>
    </div>
  )
}
