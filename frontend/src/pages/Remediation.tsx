import { useState } from 'react'
import { incidentsApi, instancesApi, remediationApi } from '../api/endpoints'
import { useApi } from '../hooks/useApi'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../context/ToastContext'
import { Card, DataNote, EmptyState, ErrorState, Field, Loading, Modal, PageHeader, SeverityBadge, StatCard } from '../components/ui'
import { Icon, Spinner } from '../components/Icon'
import { errorMessage } from '../api/client'
import { formatDateTime, timeAgo } from '../lib/format'
import type { RemediationAction, RemediationRule } from '../types'

const RISK_BADGE: Record<string, string> = {
  low: 'badge badge-low',
  medium: 'badge badge-medium',
  high: 'badge badge-high',
}

const STATUS_BADGE: Record<string, string> = {
  pending_approval: 'badge badge-medium',
  approved: 'badge badge-info',
  rejected: 'badge badge-critical',
  running: 'badge badge-info',
  succeeded: 'badge badge-success',
  failed: 'badge badge-critical',
  dry_run: 'badge badge-neutral',
}

export default function Remediation() {
  const { canOperate } = useAuth()
  const toast = useToast()
  const [requestOpen, setRequestOpen] = useState(false)
  const [ruleOpen, setRuleOpen] = useState(false)
  const [working, setWorking] = useState<number | null>(null)
  const [expanded, setExpanded] = useState<number | null>(null)
  const [request, setRequest] = useState({ action_name: 'restart_service', instance_id: '', incident_id: '', dry_run: true, reason: '' })
  const [ruleForm, setRuleForm] = useState({
    name: '',
    metric: 'cpu_percent',
    operator: '>',
    threshold: 90,
    duration_minutes: 5,
    action_name: 'restart_service',
    dry_run: true,
  })

  const catalog = useApi(() => remediationApi.catalog(), [])
  const rules = useApi(() => remediationApi.rules(), [])
  const actions = useApi(() => remediationApi.actions({ page_size: 30 }), [])
  const instances = useApi(() => instancesApi.list(), [])
  const incidents = useApi(() => incidentsApi.list({ page_size: 20, status: 'investigating' }), [])

  const pending = (actions.data?.items ?? []).filter((action) => action.status === 'pending_approval')

  async function submitRequest(event: React.FormEvent) {
    event.preventDefault()
    try {
      const created = await remediationApi.request({
        action_name: request.action_name,
        instance_id: request.instance_id ? Number(request.instance_id) : undefined,
        incident_id: request.incident_id ? Number(request.incident_id) : undefined,
        dry_run: request.dry_run,
        reason: request.reason || undefined,
      })
      toast.success(created.dry_run ? 'Dry-run completed — no change was made' : 'Approval request created')
      setRequestOpen(false)
      setRequest({ action_name: 'restart_service', instance_id: '', incident_id: '', dry_run: true, reason: '' })
      actions.reload()
      catalog.reload()
    } catch (err) {
      toast.error(errorMessage(err))
    }
  }

  async function decide(action: RemediationAction, decision: 'approve' | 'reject') {
    setWorking(action.id)
    try {
      if (decision === 'approve') await remediationApi.approve(action.id, 'Approved in remediation center')
      else await remediationApi.reject(action.id, 'Rejected in remediation center')
      toast.success(`Action ${decision === 'approve' ? 'approved' : 'rejected'}`)
      actions.reload()
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setWorking(null)
    }
  }

  async function execute(action: RemediationAction) {
    setWorking(action.id)
    try {
      const result = await remediationApi.execute(action.id)
      toast.success(`Action finished: ${result.status}`)
      actions.reload()
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setWorking(null)
    }
  }

  async function toggleRule(rule: RemediationRule) {
    try {
      await remediationApi.updateRule(rule.id, { enabled: !rule.enabled })
      rules.reload()
    } catch (err) {
      toast.error(errorMessage(err))
    }
  }

  async function deleteRule(rule: RemediationRule) {
    if (!window.confirm(`Delete rule "${rule.name}"?`)) return
    try {
      await remediationApi.deleteRule(rule.id)
      toast.success('Rule deleted')
      rules.reload()
    } catch (err) {
      toast.error(errorMessage(err))
    }
  }

  async function createRule(event: React.FormEvent) {
    event.preventDefault()
    try {
      await remediationApi.createRule({ ...ruleForm, requires_approval: true })
      toast.success('Remediation rule created')
      setRuleOpen(false)
      setRuleForm({ name: '', metric: 'cpu_percent', operator: '>', threshold: 90, duration_minutes: 5, action_name: 'restart_service', dry_run: true })
      rules.reload()
    } catch (err) {
      toast.error(errorMessage(err))
    }
  }

  async function evaluate() {
    try {
      const result = await remediationApi.evaluate()
      toast.success(`Rule evaluation completed: ${result.actions_created} action(s) created`)
      actions.reload()
    } catch (err) {
      toast.error(errorMessage(err))
    }
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Remediation center"
        subtitle="Allowlisted actions only. Dry-run by default, and production execution requires approval from a second operator."
        badge={<span className="badge badge-success"><Icon name="shield" size={11} /> destructive actions disabled</span>}
        actions={
          <>
            <button type="button" className="btn btn-secondary" onClick={evaluate} disabled={!canOperate}>
              <Icon name="activity" size={13} /> Evaluate rules
            </button>
            <button type="button" className="btn btn-primary" onClick={() => setRequestOpen(true)} disabled={!canOperate}>
              <Icon name="wrench" size={13} /> Request action
            </button>
          </>
        }
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard label="Pending approvals" value={pending.length} hint="Production actions waiting" icon="clock" tone={pending.length ? 'warning' : 'success'} />
        <StatCard label="Enabled rules" value={(rules.data ?? []).filter((rule) => rule.enabled).length} hint={`${rules.data?.length ?? 0} configured`} icon="settings" tone="info" />
        <StatCard label="Actions recorded" value={actions.data?.total ?? 0} icon="list" tone="default" />
        <StatCard label="Allowlisted actions" value={catalog.data?.length ?? 0} hint="No shell or cloud mutation" icon="shield" tone="success" />
      </div>

      {pending.length > 0 && (
        <Card title="Awaiting approval" subtitle="Approval must come from a different user than the requester" bodyClassName="divide-y">
          {pending.map((action) => (
            <div key={action.id} className="flex flex-col gap-2 px-5 py-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="text-[12.5px] font-medium text-slate-800 dark:text-slate-100">
                  {action.action_name.replace(/_/g, ' ')} → {action.target}
                </p>
                <p className="text-[11px] text-slate-500">
                  Requested by {action.requested_by} · {timeAgo(action.created_at)} · health before: {action.health_check_before ?? 'unknown'}
                </p>
              </div>
              <div className="flex gap-1.5">
                <button type="button" className="btn btn-secondary btn-xs" disabled={working === action.id || !canOperate} onClick={() => decide(action, 'reject')}>Reject</button>
                <button type="button" className="btn btn-primary btn-xs" disabled={working === action.id || !canOperate} onClick={() => decide(action, 'approve')}>
                  {working === action.id && <Spinner size={11} />} Approve
                </button>
              </div>
            </div>
          ))}
        </Card>
      )}

      <Card title="Action catalog" subtitle="The complete set of actions the engine can perform. Everything else is rejected.">
        {catalog.loading && !catalog.data ? (
          <Loading rows={3} />
        ) : (
          <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
            {(catalog.data ?? []).map((spec) => (
              <div key={spec.name} className="rounded-lg border p-3">
                <div className="flex items-start justify-between gap-2">
                  <p className="text-[12.5px] font-medium text-slate-800 dark:text-slate-100">{spec.label}</p>
                  <span className={RISK_BADGE[spec.risk]}>{spec.risk}</span>
                </div>
                <p className="mt-1 font-mono text-[10.5px] text-slate-500">{spec.name}</p>
                <p className="mt-1 text-[11.5px] leading-relaxed text-slate-600 dark:text-slate-300">{spec.description}</p>
                <div className="mt-1.5 flex flex-wrap gap-1">
                  <span className="badge badge-neutral">dry-run</span>
                  {spec.requires_approval && <span className="badge badge-medium">approval required</span>}
                  {spec.categories.map((category) => <span key={category} className="badge badge-neutral">{category}</span>)}
                </div>
              </div>
            ))}
          </div>
        )}
        <DataNote>
          Not implemented by design: terminate instance, delete bucket, modify IAM policy, change security group, run arbitrary
          shell. Those requests are rejected before any record is created.
        </DataNote>
      </Card>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card
          title="Remediation rules"
          subtitle="Rule-based triggers evaluated by the scheduler"
          actions={canOperate && <button type="button" className="btn btn-secondary btn-xs" onClick={() => setRuleOpen(true)}><Icon name="plus" size={11} /> New rule</button>}
          bodyClassName=""
        >
          {rules.loading && !rules.data ? (
            <div className="p-4"><Loading rows={4} /></div>
          ) : (rules.data ?? []).length === 0 ? (
            <EmptyState title="No rules" description="Create a rule to automate detection-to-action proposals." icon="settings" />
          ) : (
            <div className="overflow-x-auto">
              <table className="table">
                <thead><tr><th>Rule</th><th>Condition</th><th>Action</th><th>Enabled</th><th /></tr></thead>
                <tbody>
                  {rules.data!.map((rule) => (
                    <tr key={rule.id}>
                      <td>
                        <p className="text-[12px] font-medium">{rule.name}</p>
                        <p className="text-[10.5px] text-slate-500">{rule.enabled ? 'active' : 'paused'} · dry-run {rule.dry_run ? 'on' : 'off'}</p>
                      </td>
                      <td className="whitespace-nowrap text-[11px]">{rule.metric.replace('_percent', '')} {rule.operator} {rule.threshold}% for {rule.duration_minutes}m</td>
                      <td className="font-mono text-[10.5px]">{rule.action_name}</td>
                      <td>
                        <input type="checkbox" className="h-3.5 w-3.5" checked={rule.enabled} disabled={!canOperate} onChange={() => toggleRule(rule)} />
                      </td>
                      <td className="text-right">
                        <button type="button" className="btn btn-ghost btn-xs text-rose-500" disabled={!canOperate} onClick={() => deleteRule(rule)}>
                          <Icon name="trash" size={12} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <Card title="Execution history" subtitle="Dry-runs and approved executions, newest first" bodyClassName="">
          {actions.loading && !actions.data ? (
            <div className="p-4"><Loading rows={4} /></div>
          ) : (actions.data?.items ?? []).length === 0 ? (
            <EmptyState title="No actions yet" description="Request a dry-run to see how the audit trail is recorded." icon="wrench" />
          ) : (
            <div className="max-h-[420px] overflow-y-auto">
              <table className="table">
                <thead><tr><th>Action</th><th>Status</th><th>When</th><th /></tr></thead>
                <tbody>
                  {actions.data!.items.map((action) => (
                    <tr key={action.id}>
                      <td>
                        <p className="text-[12px] font-medium">{action.action_name.replace(/_/g, ' ')}</p>
                        <p className="text-[10.5px] text-slate-500">{action.target} · {action.requested_by}</p>
                      </td>
                      <td><span className={STATUS_BADGE[action.status] ?? 'badge badge-neutral'}>{action.status.replace('_', ' ')}</span></td>
                      <td className="whitespace-nowrap text-[10.5px] text-slate-500">{timeAgo(action.created_at)}</td>
                      <td className="text-right">
                        {(action.status === 'approved' || action.status === 'dry_run') && canOperate && (
                          <button type="button" className="btn btn-primary btn-xs" disabled={working === action.id} onClick={() => execute(action)}>
                            {working === action.id ? <Spinner size={11} /> : 'Execute'}
                          </button>
                        )}
                        <button type="button" className="btn btn-ghost btn-xs" onClick={() => setExpanded(expanded === action.id ? null : action.id)}>
                          <Icon name="eye" size={12} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>

      {expanded !== null && (
        <Card
          title={`Action #${expanded} output`}
          subtitle="Full execution record including health checks"
          actions={<button type="button" className="btn btn-ghost btn-xs" onClick={() => setExpanded(null)}><Icon name="close" size={12} /></button>}
        >
          {(() => {
            const action = actions.data?.items.find((item) => item.id === expanded)
            if (!action) return <p className="text-xs text-slate-500">Action not found in the current page.</p>
            return (
              <div className="space-y-2">
                <div className="flex flex-wrap gap-2 text-[11px]">
                  <span className={STATUS_BADGE[action.status] ?? 'badge badge-neutral'}>{action.status}</span>
                  <span className="badge badge-neutral">dry-run: {String(action.dry_run)}</span>
                  <span className="badge badge-neutral">health before: {action.health_check_before ?? '—'}</span>
                  <span className="badge badge-neutral">health after: {action.health_check_after ?? '—'}</span>
                  <span className="badge badge-neutral">approved by: {action.approved_by ?? '—'}</span>
                  <span className="badge badge-neutral">executed: {formatDateTime(action.executed_at)}</span>
                </div>
                <pre className="code-block whitespace-pre-wrap">{action.output ?? action.error ?? 'No output recorded.'}</pre>
              </div>
            )
          })()}
        </Card>
      )}

      <Modal
        open={requestOpen}
        onClose={() => setRequestOpen(false)}
        title="Request a remediation action"
        subtitle="Dry-run validates targeting without changing anything. Real execution always needs approval."
        footer={
          <>
            <button type="button" className="btn btn-secondary" onClick={() => setRequestOpen(false)}>Cancel</button>
            <button type="submit" form="request-form" className="btn btn-primary">Submit</button>
          </>
        }
      >
        <form id="request-form" onSubmit={submitRequest} className="space-y-3">
          <Field label="Action">
            <select className="input" value={request.action_name} onChange={(event) => setRequest({ ...request, action_name: event.target.value })}>
              {(catalog.data ?? []).map((spec) => (
                <option key={spec.name} value={spec.name}>{spec.label} ({spec.risk} risk)</option>
              ))}
            </select>
          </Field>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Target instance">
              <select className="input" value={request.instance_id} onChange={(event) => setRequest({ ...request, instance_id: event.target.value })}>
                <option value="">No specific instance</option>
                {(instances.data ?? []).map((instance) => (
                  <option key={instance.id} value={instance.id}>{instance.name} ({instance.source})</option>
                ))}
              </select>
            </Field>
            <Field label="Link to incident">
              <select className="input" value={request.incident_id} onChange={(event) => setRequest({ ...request, incident_id: event.target.value })}>
                <option value="">None</option>
                {(incidents.data?.items ?? []).map((incident) => (
                  <option key={incident.id} value={incident.id}>{incident.incident_number} · {incident.title}</option>
                ))}
              </select>
            </Field>
          </div>
          <Field label="Reason" hint="Recorded in the audit trail.">
            <textarea className="input h-20" value={request.reason} onChange={(event) => setRequest({ ...request, reason: event.target.value })} placeholder="Why is this action required?" />
          </Field>
          <label className="flex items-start gap-2 rounded-lg border px-3 py-2">
            <input type="checkbox" className="mt-0.5 h-3.5 w-3.5" checked={request.dry_run} onChange={(event) => setRequest({ ...request, dry_run: event.target.checked })} />
            <span>
              <span className="block text-[12px] font-medium">Dry-run</span>
              <span className="block text-[11px] text-slate-500">Recommended. Validates the target and captures a plan without executing.</span>
            </span>
          </label>
        </form>
      </Modal>

      <Modal
        open={ruleOpen}
        onClose={() => setRuleOpen(false)}
        title="New remediation rule"
        subtitle="Thresholds are evaluated against the most recent telemetry samples."
        footer={
          <>
            <button type="button" className="btn btn-secondary" onClick={() => setRuleOpen(false)}>Cancel</button>
            <button type="submit" form="rule-form" className="btn btn-primary">Create rule</button>
          </>
        }
      >
        <form id="rule-form" onSubmit={createRule} className="space-y-3">
          <Field label="Name">
            <input required minLength={3} className="input" value={ruleForm.name} onChange={(event) => setRuleForm({ ...ruleForm, name: event.target.value })} placeholder="Restart on sustained CPU saturation" />
          </Field>
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Signal">
              <select className="input" value={ruleForm.metric} onChange={(event) => setRuleForm({ ...ruleForm, metric: event.target.value })}>
                <option value="cpu_percent">cpu_percent</option>
                <option value="memory_percent">memory_percent</option>
                <option value="disk_percent">disk_percent</option>
                <option value="network_in_kbps">network_in_kbps</option>
              </select>
            </Field>
            <Field label="Operator">
              <select className="input" value={ruleForm.operator} onChange={(event) => setRuleForm({ ...ruleForm, operator: event.target.value })}>
                <option value=">">&gt;</option>
                <option value=">=">&gt;=</option>
                <option value="<">&lt;</option>
                <option value="<=">&lt;=</option>
              </select>
            </Field>
            <Field label="Threshold">
              <input type="number" className="input" value={ruleForm.threshold} onChange={(event) => setRuleForm({ ...ruleForm, threshold: Number(event.target.value) })} />
            </Field>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Duration (minutes)">
              <input type="number" min={1} max={240} className="input" value={ruleForm.duration_minutes} onChange={(event) => setRuleForm({ ...ruleForm, duration_minutes: Number(event.target.value) })} />
            </Field>
            <Field label="Action">
              <select className="input" value={ruleForm.action_name} onChange={(event) => setRuleForm({ ...ruleForm, action_name: event.target.value })}>
                {(catalog.data ?? []).map((spec) => <option key={spec.name} value={spec.name}>{spec.label}</option>)}
              </select>
            </Field>
          </div>
          <label className="flex items-center gap-2 text-[12px]">
            <input type="checkbox" className="h-3.5 w-3.5" checked={ruleForm.dry_run} onChange={(event) => setRuleForm({ ...ruleForm, dry_run: event.target.checked })} />
            Create triggered actions as dry-runs
          </label>
        </form>
      </Modal>
    </div>
  )
}
