import { useState } from 'react'
import { deploymentsApi } from '../api/endpoints'
import { useApi } from '../hooks/useApi'
import { Card, DataNote, EmptyState, ErrorState, Loading, PageHeader, Pagination, SourceBadge, StatCard } from '../components/ui'
import { Icon } from '../components/Icon'
import { formatDateTime, timeAgo } from '../lib/format'

const STATUS_BADGE: Record<string, string> = {
  success: 'badge badge-success',
  failed: 'badge badge-critical',
  running: 'badge badge-info',
  cancelled: 'badge badge-neutral',
}

export default function Pipelines() {
  const [environment, setEnvironment] = useState('')
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)

  const summary = useApi(() => deploymentsApi.summary(), [])
  const pipelines = useApi(() => deploymentsApi.pipelines(), [])
  const deployments = useApi(
    () => deploymentsApi.list({ page, page_size: 15, environment: environment || undefined, status: status || undefined }),
    [page, environment, status],
  )

  return (
    <div className="space-y-4">
      <PageHeader
        title="CI/CD pipelines"
        subtitle="Pipeline definitions detected from this repository, with deployment history ingested from CI or seeded for demonstration."
        actions={
          <button type="button" className="btn btn-secondary" onClick={() => { summary.reload(); pipelines.reload(); deployments.reload(); }}>
            <Icon name="refresh" size={13} /> Refresh
          </button>
        }
      />

      {summary.loading && !summary.data ? (
        <Loading rows={4} />
      ) : summary.error ? (
        <ErrorState message={summary.error} onRetry={summary.reload} />
      ) : (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <StatCard label="Total deployments" value={summary.data?.total_deployments ?? 0} hint={`${summary.data?.deployments_last_7_days ?? 0} in the last 7 days`} icon="git" tone="info" />
          <StatCard label="Success rate" value={`${summary.data?.success_rate ?? 0}%`} hint={`${summary.data?.successful ?? 0} successful`} icon="check" tone="success" />
          <StatCard label="Failed" value={summary.data?.failed ?? 0} hint="Review stage and commit" icon="alert" tone="critical" />
          <StatCard
            label="Last deployment"
            value={String(summary.data?.last_deployment?.status ?? '—')}
            hint={summary.data?.last_deployment ? `${summary.data.last_deployment.service} ${summary.data.last_deployment.version}` : 'No runs recorded'}
            icon="clock"
            tone="default"
          />
        </div>
      )}

      <div className="grid gap-3 md:grid-cols-2">
        {(pipelines.data ?? []).map((pipeline) => (
          <Card key={pipeline.name}>
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="flex items-center gap-2 text-[13px] font-semibold text-slate-900 dark:text-slate-50">
                  {pipeline.name}
                  <span className={`badge ${pipeline.detected ? 'badge-success' : 'badge-neutral'}`}>
                    {pipeline.detected ? 'config detected' : 'config missing'}
                  </span>
                </p>
                <p className="mt-0.5 font-mono text-[10.5px] text-slate-500">{pipeline.config_path}</p>
              </div>
              <span className="badge badge-info">{pipeline.platform}</span>
            </div>

            <div className="mt-2 flex flex-wrap gap-1">
              {pipeline.stages.map((stage) => (
                <span key={stage} className="badge badge-neutral font-mono text-[10px]">{stage}</span>
              ))}
            </div>

            <div className="mt-3 flex items-center justify-between border-t pt-2 text-[11px] text-slate-500">
              <span>{pipeline.total_runs} runs · {pipeline.success_rate}% success</span>
              {pipeline.last_run ? (
                <span className="flex items-center gap-1.5">
                  <span className={STATUS_BADGE[pipeline.last_run.status] ?? 'badge badge-neutral'}>{pipeline.last_run.status}</span>
                  <span>{timeAgo(pipeline.last_run.started_at)}</span>
                </span>
              ) : (
                <span>no runs recorded</span>
              )}
            </div>
          </Card>
        ))}
      </div>

      <Card title="Deployment history" subtitle="Deployments reported by CI or seeded as simulated examples" bodyClassName="">
        <div className="flex flex-wrap items-end gap-2 border-b px-4 py-3">
          <div>
            <label className="label" htmlFor="deploy-env">Environment</label>
            <select id="deploy-env" className="input w-40" value={environment} onChange={(event) => { setEnvironment(event.target.value); setPage(1) }}>
              <option value="">All</option>
              <option value="production">production</option>
              <option value="staging">staging</option>
              <option value="development">development</option>
            </select>
          </div>
          <div>
            <label className="label" htmlFor="deploy-status">Status</label>
            <select id="deploy-status" className="input w-36" value={status} onChange={(event) => { setStatus(event.target.value); setPage(1) }}>
              <option value="">All</option>
              <option value="success">success</option>
              <option value="failed">failed</option>
              <option value="running">running</option>
            </select>
          </div>
        </div>

        {deployments.loading && !deployments.data ? (
          <div className="p-4"><Loading rows={5} /></div>
        ) : deployments.error ? (
          <div className="p-4"><ErrorState message={deployments.error} onRetry={deployments.reload} /></div>
        ) : deployments.data?.items.length === 0 ? (
          <EmptyState title="No deployments match" description="Adjust the filters or send a deployment from your pipeline." icon="git" />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="table">
                <thead>
                  <tr><th>Service</th><th>Version</th><th>Environment</th><th>Status</th><th>Stage</th><th>Pipeline</th><th>Source</th><th>Started</th><th>Duration</th></tr>
                </thead>
                <tbody>
                  {deployments.data!.items.map((deployment) => (
                    <tr key={deployment.id}>
                      <td className="font-medium">{deployment.service}</td>
                      <td className="font-mono text-[11px]">{deployment.version}</td>
                      <td className="text-xs">{deployment.environment}</td>
                      <td><span className={STATUS_BADGE[deployment.status] ?? 'badge badge-neutral'}>{deployment.status}</span></td>
                      <td className="text-[11px]">{deployment.stage}</td>
                      <td className="text-[11px]">{deployment.pipeline}</td>
                      <td><SourceBadge source={deployment.source} /></td>
                      <td className="whitespace-nowrap text-[11px] text-slate-500">{formatDateTime(deployment.started_at)}</td>
                      <td className="text-[11px]">{deployment.duration_seconds}s</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="px-4 pb-3">
              <Pagination page={deployments.data?.page ?? 1} pages={deployments.data?.pages ?? 1} total={deployments.data?.total ?? 0} onPage={setPage} />
            </div>
          </>
        )}
      </Card>

      <DataNote>
        Pipeline definitions come from real files in this repository: <span className="font-mono">.github/workflows/ci.yml</span>,{' '}
        <span className="font-mono">release.yml</span>, <span className="font-mono">Jenkinsfile</span> and{' '}
        <span className="font-mono">infra/terraform</span>. Deployment rows posted by a real pipeline are stored with{' '}
        <span className="font-mono">source=pipeline</span>; seeded demonstration rows are marked{' '}
        <span className="font-mono">simulated</span>.
      </DataNote>
    </div>
  )
}
