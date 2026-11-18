import { useState } from 'react'
import { awsApi } from '../api/endpoints'
import { useApi } from '../hooks/useApi'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../context/ToastContext'
import { Card, DataNote, EmptyState, ErrorState, Loading, PageHeader, SourceBadge, Tabs } from '../components/ui'
import { Icon } from '../components/Icon'
import { errorMessage } from '../api/client'
import { formatDateTime } from '../lib/format'
import type { AwsResource } from '../types'

const MODE_STYLE: Record<string, string> = {
  simulated: 'border-amber-400/50 bg-amber-50 dark:border-amber-500/30 dark:bg-amber-950/30',
  connected: 'border-emerald-400/50 bg-emerald-50 dark:border-emerald-500/30 dark:bg-emerald-950/30',
  not_configured: 'border-slate-300 bg-slate-50 dark:border-slate-700 dark:bg-slate-900',
  error: 'border-rose-400/50 bg-rose-50 dark:border-rose-500/30 dark:bg-rose-950/30',
}

export default function Aws() {
  const { isAdmin } = useAuth()
  const toast = useToast()
  const [tab, setTab] = useState('ec2')

  const status = useApi(() => awsApi.status(), [])
  const guide = useApi(() => awsApi.guide(), [])
  const ec2 = useApi(() => awsApi.ec2(), [])
  const s3 = useApi(() => awsApi.s3(), [])
  const iam = useApi(() => awsApi.iam(), [])
  const sg = useApi(() => awsApi.securityGroups(), [])

  const datasets: Record<string, { data: { items: AwsResource[]; source: string } | null; loading: boolean; reload: () => void; error: string | null }> = {
    ec2: { data: ec2.data ?? null, loading: ec2.loading, reload: ec2.reload, error: ec2.error },
    s3: { data: s3.data ?? null, loading: s3.loading, reload: s3.reload, error: s3.error },
    iam: { data: iam.data ?? null, loading: iam.loading, reload: iam.reload, error: iam.error },
    securityGroups: { data: sg.data ?? null, loading: sg.loading, reload: sg.reload, error: sg.error },
  }
  const active = datasets[tab]

  async function refresh() {
    try {
      const result = await awsApi.refresh()
      toast.success(`Connection re-checked: ${result.mode}`)
      status.reload()
      ec2.reload()
      s3.reload()
      iam.reload()
      sg.reload()
    } catch (err) {
      toast.error(errorMessage(err))
    }
  }

  const mode = status.data?.mode ?? 'simulated'

  return (
    <div className="space-y-4">
      <PageHeader
        title="AWS integrations"
        subtitle="Optional, read-only AWS inventory. Simulation mode is the default and is labelled on every record."
        actions={
          isAdmin && (
            <button type="button" className="btn btn-secondary" onClick={refresh}>
              <Icon name="refresh" size={13} /> Re-check connection
            </button>
          )
        }
      />

      {status.loading && !status.data ? (
        <Loading rows={3} />
      ) : status.error ? (
        <ErrorState message={status.error} onRetry={status.reload} />
      ) : status.data ? (
        <div className={`rounded-xl border p-4 ${MODE_STYLE[mode]}`}>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="flex items-center gap-2 text-[13px] font-semibold text-slate-900 dark:text-slate-50">
                <Icon name="cloud" size={15} />
                Connection mode: <span className="uppercase tracking-wide">{status.data.mode}</span>
              </p>
              <p className="mt-1 max-w-3xl text-[12px] leading-relaxed text-slate-600 dark:text-slate-300">{status.data.message}</p>
            </div>
            <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-[11.5px]">
              <div><dt className="text-slate-500">Region</dt><dd className="font-medium">{status.data.region}</dd></div>
              <div><dt className="text-slate-500">Account</dt><dd className="font-medium">{status.data.account_id ?? 'not connected'}</dd></div>
              <div className="col-span-2"><dt className="text-slate-500">Checked</dt><dd className="font-medium">{formatDateTime(status.data.checked_at)}</dd></div>
            </dl>
          </div>
          {status.data.identity && <p className="mt-2 break-all font-mono text-[10.5px] text-slate-500">{status.data.identity}</p>}
        </div>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-3">
        <Card title="How to connect a real account" subtitle="Read-only, credentials stay in the environment" className="xl:col-span-2">
          {(guide.data?.steps ?? []).length === 0 ? (
            <Loading rows={3} />
          ) : (
            <ol className="space-y-2">
              {guide.data!.steps.map((step, index) => (
                <li key={step} className="flex gap-2 text-[12px] leading-relaxed text-slate-700 dark:text-slate-200">
                  <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand-600 text-[10px] font-semibold text-white">{index + 1}</span>
                  {step}
                </li>
              ))}
            </ol>
          )}
          <DataNote>
            {guide.data?.safety.join(' ') ?? 'No mutating AWS API is implemented in this build.'}
          </DataNote>
        </Card>

        <Card title="Permissions requested" subtitle="Least privilege for inventory and analysis">
          <ul className="space-y-1">
            {(guide.data?.permissions_used ?? []).map((permission) => (
              <li key={permission} className="font-mono text-[11px] text-slate-600 dark:text-slate-300">{permission}</li>
            ))}
          </ul>
        </Card>
      </div>

      <Card bodyClassName="">
        <div className="px-4 pt-3">
          <Tabs
            tabs={[
              { id: 'ec2', label: 'EC2', count: ec2.data?.count },
              { id: 's3', label: 'S3', count: s3.data?.count },
              { id: 'iam', label: 'IAM policies', count: iam.data?.count },
              { id: 'securityGroups', label: 'Security groups', count: sg.data?.count },
            ]}
            active={tab}
            onChange={setTab}
          />
        </div>

        {active.loading && !active.data ? (
          <div className="p-4"><Loading rows={6} /></div>
        ) : active.error ? (
          <div className="p-4"><ErrorState message={active.error} onRetry={active.reload} /></div>
        ) : !active.data || active.data.items.length === 0 ? (
          <EmptyState title="No resources" description="This inventory is empty in the current mode." icon="cloud" />
        ) : (
          <div className="overflow-x-auto">
            <table className="table">
              <thead>
                <tr><th>Name</th><th>Resource ID</th><th>State</th><th>Region</th><th>Details</th><th>Source</th></tr>
              </thead>
              <tbody>
                {active.data.items.map((item) => (
                  <tr key={`${item.type}-${item.resource_id}`}>
                    <td className="font-medium">{item.name}</td>
                    <td className="max-w-[240px] truncate font-mono text-[10.5px] text-slate-500" title={item.resource_id}>{item.resource_id}</td>
                    <td className="text-xs">{item.state ?? '—'}</td>
                    <td className="text-xs">{item.region}</td>
                    <td className="max-w-[420px]">
                      {tab === 's3' ? (
                        <div className="flex flex-wrap gap-1">
                          <span className={`badge ${item.detail.public_access_block?.BlockPublicAcls ? 'badge-success' : 'badge-critical'}`}>
                            {item.detail.public_access_block?.BlockPublicAcls ? 'block public' : 'public risk'}
                          </span>
                          <span className={`badge ${item.detail.encryption ? 'badge-success' : 'badge-medium'}`}>{item.detail.encryption ? 'encrypted' : 'no encryption'}</span>
                          <span className={`badge ${item.detail.public_acl ? 'badge-critical' : 'badge-neutral'}`}>{item.detail.public_acl ? 'public ACL' : 'private ACL'}</span>
                        </div>
                      ) : tab === 'iam' ? (
                        <ul className="list-inside list-disc text-[11px] text-slate-600 dark:text-slate-300">
                          {(item.detail.issues ?? []).map((issue: string) => <li key={issue}>{issue}</li>)}
                        </ul>
                      ) : tab === 'securityGroups' ? (
                        <div className="space-y-0.5 text-[10.5px] text-slate-600 dark:text-slate-300">
                          {(item.detail.ingress ?? []).map((rule: any, index: number) => (
                            <p key={index} className="font-mono">
                              {rule.protocol}:{rule.from_port}-{rule.to_port} ← {(rule.cidrs ?? []).join(', ') || 'no CIDR'}
                            </p>
                          ))}
                        </div>
                      ) : (
                        <span className="text-[11px] text-slate-600 dark:text-slate-300">
                          {item.detail.private_ip ?? '—'} · {item.detail.environment ?? item.detail.vpc_id ?? '—'}
                        </span>
                      )}
                    </td>
                    <td><SourceBadge source={item.source} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <DataNote>
        CloudWatch metrics are only queried when the connection mode is <span className="font-medium">connected</span>; otherwise the
        endpoint returns an explicit message instead of fabricated datapoints. No resource is created, modified or deleted by this module.
      </DataNote>
    </div>
  )
}
