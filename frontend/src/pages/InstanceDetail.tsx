import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { instancesApi, monitoringApi } from '../api/endpoints'
import { useApi } from '../hooks/useApi'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../context/ToastContext'
import { AreaTrend } from '../components/Charts'
import { Card, DataNote, EmptyState, ErrorState, HealthBadge, Loading, PageHeader, SeverityBadge, SourceBadge, StatCard } from '../components/ui'
import { Icon } from '../components/Icon'
import { errorMessage } from '../api/client'
import { formatDuration, formatMoney, formatNumber, formatPercent, formatTime, timeAgo } from '../lib/format'

export default function InstanceDetail() {
  const { id } = useParams<{ id: string }>()
  const instanceId = Number(id)
  const navigate = useNavigate()
  const { canOperate } = useAuth()
  const toast = useToast()
  const [hours, setHours] = useState(6)

  const detail = useApi(() => instancesApi.get(instanceId), [instanceId], { pollMs: 30_000 })
  const metrics = useApi(() => instancesApi.metrics(instanceId, hours), [instanceId, hours, detail.data?.latest_metric?.timestamp])

  if (Number.isNaN(instanceId)) {
    return <ErrorState message="Invalid instance id" />
  }

  if (detail.loading && !detail.data) {
    return (
      <div>
        <PageHeader title="Instance" subtitle="Loading instance detail…" />
        <Loading rows={6} />
      </div>
    )
  }

  if (detail.error || !detail.data) {
    return (
      <div>
        <PageHeader title="Instance" actions={<Link to="/instances" className="btn btn-secondary">Back to inventory</Link>} />
        <ErrorState message={detail.error ?? 'Instance not found'} onRetry={detail.reload} />
      </div>
    )
  }

  const { instance, latest_metric: metric, alerts, statistics, data_note: dataNote } = detail.data
  const series = (metrics.data ?? []).map((point) => ({
    label: formatTime(point.timestamp),
    cpu: point.cpu_percent,
    memory: point.memory_percent,
    disk: point.disk_percent,
    network: point.network_in_kbps,
  }))

  async function power(action: 'start' | 'stop') {
    try {
      await instancesApi.power(instanceId, action)
      toast.success(`Instance ${action === 'stop' ? 'stopped' : 'started'} (simulated)`)
      detail.reload()
    } catch (err) {
      toast.error(errorMessage(err))
    }
  }

  async function collectNow() {
    try {
      await monitoringApi.collect()
      toast.success('Collection cycle completed')
      detail.reload()
      metrics.reload()
    } catch (err) {
      toast.error(errorMessage(err))
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-xs text-slate-500">
        <Link to="/instances" className="hover:text-brand-600">Infrastructure</Link>
        <Icon name="chevron" size={11} />
        <span className="text-slate-700 dark:text-slate-300">{instance.name}</span>
      </div>

      <PageHeader
        title={instance.name}
        subtitle={`${instance.instance_type} · ${instance.region} · ${instance.environment}`}
        badge={
          <span className="flex items-center gap-1.5">
            <HealthBadge value={instance.health_status} />
            <SourceBadge source={instance.source} />
          </span>
        }
        actions={
          <>
            <button type="button" className="btn btn-secondary" onClick={collectNow}>
              <Icon name="refresh" size={13} /> Collect now
            </button>
            {canOperate && instance.source === 'simulated' && (
              <>
                {instance.status === 'running' ? (
                  <button type="button" className="btn btn-secondary" onClick={() => power('stop')}>
                    <Icon name="stop" size={12} /> Stop (simulated)
                  </button>
                ) : (
                  <button type="button" className="btn btn-secondary" onClick={() => power('start')}>
                    <Icon name="play" size={12} /> Start (simulated)
                  </button>
                )}
              </>
            )}
            <button type="button" className="btn btn-primary" onClick={() => navigate('/monitoring')}>
              <Icon name="activity" size={13} /> Monitoring
            </button>
          </>
        }
      />

      <DataNote>{dataNote}</DataNote>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard label="CPU" value={formatPercent(metric?.cpu_percent)} hint={`Avg ${formatPercent(statistics.avg_cpu)} · peak ${formatPercent(statistics.peak_cpu)}`} icon="activity" tone="info" />
        <StatCard label="Memory" value={formatPercent(metric?.memory_percent)} hint={`Avg ${formatPercent(statistics.avg_memory)}`} icon="database" tone="info" />
        <StatCard label="Disk" value={formatPercent(metric?.disk_percent)} hint={`${instance.disk_gb} GB provisioned`} icon="server" tone="default" />
        <StatCard label="Uptime" value={formatDuration((metric?.uptime_seconds ?? 0) / 60)} hint={metric ? `Load ${formatNumber(metric.load_avg_1m, 2)} · ${metric.process_count} processes` : 'No sample yet'} icon="clock" tone="success" />
      </div>

      <Card
        title="Resource utilisation"
        subtitle={`${statistics.samples} stored samples · latest at ${timeAgo(metric?.timestamp)}`}
        actions={
          <div className="flex gap-1">
            {[1, 6, 24, 72].map((option) => (
              <button
                key={option}
                type="button"
                className={`btn btn-xs ${hours === option ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setHours(option)}
              >
                {option}h
              </button>
            ))}
          </div>
        }
      >
        {metrics.loading && !metrics.data ? (
          <Loading rows={4} />
        ) : series.length === 0 ? (
          <EmptyState title="No samples in this window" description="Run a collection cycle or widen the time range." icon="activity" />
        ) : (
          <AreaTrend
            data={series}
            xKey="label"
            height={280}
            series={[
              { key: 'cpu', label: 'CPU %', color: '#3186fb' },
              { key: 'memory', label: 'Memory %', color: '#8b5cf6' },
              { key: 'disk', label: 'Disk %', color: '#f59e0b' },
            ]}
          />
        )}
        <p className="mt-2 text-[11px] text-slate-500">
          Each point is one stored telemetry sample ({instance.source === 'local' ? 'psutil' : 'simulator'} at{' '}
          {metric ? 'the configured interval' : '—'}).
        </p>
      </Card>

      <div className="grid gap-4 xl:grid-cols-3">
        <Card title="Instance metadata" className="xl:col-span-2">
          <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-[12.5px] sm:grid-cols-3">
            {[
              ['Instance ID', instance.external_id ?? '—'],
              ['Provider', instance.provider],
              ['State', instance.status],
              ['Hostname', instance.hostname ?? '—'],
              ['Operating system', instance.os_name ?? '—'],
              ['Private IP', instance.private_ip ?? '—'],
              ['Public IP', instance.public_ip ?? '—'],
              ['vCPU', String(instance.cpu_cores)],
              ['Memory', `${formatNumber(instance.memory_mb / 1024, 1)} GB`],
              ['Disk', `${instance.disk_gb} GB`],
              ['Estimated cost', formatMoney(instance.monthly_cost_usd)],
              ['Last seen', timeAgo(instance.last_seen_at)],
            ].map(([label, value]) => (
              <div key={label}>
                <dt className="text-[11px] uppercase tracking-wide text-slate-500">{label}</dt>
                <dd className="mt-0.5 font-medium text-slate-800 dark:text-slate-100">{value}</dd>
              </div>
            ))}
          </dl>
          {Object.keys(instance.tags ?? {}).length > 0 && (
            <div className="mt-4 border-t pt-3">
              <p className="mb-1.5 text-[11px] uppercase tracking-wide text-slate-500">Tags</p>
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(instance.tags).map(([key, value]) => (
                  <span key={key} className="badge badge-neutral font-mono">{key}={String(value)}</span>
                ))}
              </div>
            </div>
          )}
        </Card>

        <Card title="Threshold breaches" subtitle="Evaluated against the latest sample">
          {alerts.length === 0 ? (
            <EmptyState title="All signals normal" description="No threshold is currently breached." icon="check" />
          ) : (
            <ul className="space-y-2">
              {alerts.map((alert) => (
                <li key={alert.metric} className="rounded-lg border px-3 py-2">
                  <div className="flex items-center justify-between">
                    <span className="text-[12.5px] font-medium text-slate-800 dark:text-slate-100">{alert.display_name}</span>
                    <SeverityBadge value={alert.level} />
                  </div>
                  <p className="mt-1 text-[11px] text-slate-500">
                    {formatNumber(alert.value)} {alert.unit} · threshold {formatNumber(alert.threshold)} {alert.unit}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  )
}
