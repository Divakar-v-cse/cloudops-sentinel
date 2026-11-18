import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { costApi, instancesApi, monitoringApi } from '../api/endpoints'
import { useApi, useDebounced } from '../hooks/useApi'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../context/ToastContext'
import { Card, DataNote, EmptyState, ErrorState, Field, HealthBadge, Loading, Modal, PageHeader, SourceBadge, UsageBar } from '../components/ui'
import { Icon } from '../components/Icon'
import { errorMessage } from '../api/client'
import { formatMoney, timeAgo } from '../lib/format'

interface CreateForm {
  name: string
  instance_type: string
  environment: string
  region: string
  cpu_cores: number
  memory_mb: number
  disk_gb: number
  role: string
}

const EMPTY_FORM: CreateForm = {
  name: '',
  instance_type: 't3.medium',
  environment: 'development',
  region: 'us-east-1',
  cpu_cores: 2,
  memory_mb: 4096,
  disk_gb: 50,
  role: 'web',
}

export default function Instances() {
  const { canOperate } = useAuth()
  const toast = useToast()
  const [search, setSearch] = useState('')
  const [source, setSource] = useState('')
  const [environment, setEnvironment] = useState('')
  const [health, setHealth] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [form, setForm] = useState<CreateForm>(EMPTY_FORM)
  const [saving, setSaving] = useState(false)
  const debounced = useDebounced(search)

  const fleet = useApi(() => monitoringApi.fleet(), [], { pollMs: 30_000 })
  const pricing = useApi(() => costApi.pricing(), [], { enabled: createOpen })

  const rows = useMemo(() => {
    const list = fleet.data ?? []
    return list.filter((row) => {
      const instance = row.instance
      if (source && instance.source !== source) return false
      if (environment && instance.environment !== environment) return false
      if (health && instance.health_status !== health) return false
      if (debounced) {
        const term = debounced.toLowerCase()
        const haystack = `${instance.name} ${instance.hostname ?? ''} ${instance.external_id ?? ''} ${instance.instance_type}`.toLowerCase()
        if (!haystack.includes(term)) return false
      }
      return true
    })
  }, [fleet.data, source, environment, health, debounced])

  async function submitCreate(event: React.FormEvent) {
    event.preventDefault()
    setSaving(true)
    try {
      await instancesApi.create({
        name: form.name,
        instance_type: form.instance_type,
        environment: form.environment,
        region: form.region,
        cpu_cores: Number(form.cpu_cores),
        memory_mb: Number(form.memory_mb),
        disk_gb: Number(form.disk_gb),
        simulate: true,
        tags: { role: form.role },
      })
      toast.success(`Simulated instance ${form.name} created`)
      setCreateOpen(false)
      setForm(EMPTY_FORM)
      fleet.reload()
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  async function power(id: number, action: 'start' | 'stop', name: string) {
    if (action === 'stop' && !window.confirm(`Stop ${name}? This only changes the simulated state; no cloud API is called.`)) return
    try {
      await instancesApi.power(id, action)
      toast.success(`${name} ${action === 'stop' ? 'stopped' : 'started'} (simulated)`)
      fleet.reload()
    } catch (err) {
      toast.error(errorMessage(err))
    }
  }

  async function remove(id: number, name: string) {
    if (!window.confirm(`Remove the simulated inventory row for ${name}? Telemetry for it is deleted.`)) return
    try {
      await instancesApi.remove(id)
      toast.success(`${name} removed from inventory`)
      fleet.reload()
    } catch (err) {
      toast.error(errorMessage(err))
    }
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Infrastructure inventory"
        subtitle="Every monitored resource with its data provenance, current health and latest resource utilisation."
        actions={
          canOperate && (
            <button type="button" className="btn btn-primary" onClick={() => setCreateOpen(true)}>
              <Icon name="plus" size={13} /> Add simulated instance
            </button>
          )
        }
      />

      <Card bodyClassName="px-4 py-3">
        <div className="flex flex-wrap items-end gap-2">
          <div className="min-w-[210px] flex-1">
            <label className="label" htmlFor="instance-search">Search</label>
            <div className="relative">
              <span className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400">
                <Icon name="search" size={14} />
              </span>
              <input
                id="instance-search"
                className="input pl-8"
                placeholder="Name, hostname or instance ID"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
            </div>
          </div>
          <div>
            <label className="label" htmlFor="source-filter">Source</label>
            <select id="source-filter" className="input w-36" value={source} onChange={(event) => setSource(event.target.value)}>
              <option value="">All sources</option>
              <option value="local">Local (psutil)</option>
              <option value="simulated">Simulated</option>
              <option value="aws">AWS</option>
            </select>
          </div>
          <div>
            <label className="label" htmlFor="env-filter">Environment</label>
            <select id="env-filter" className="input w-36" value={environment} onChange={(event) => setEnvironment(event.target.value)}>
              <option value="">All</option>
              <option value="production">production</option>
              <option value="staging">staging</option>
              <option value="development">development</option>
              <option value="local">local</option>
            </select>
          </div>
          <div>
            <label className="label" htmlFor="health-filter">Health</label>
            <select id="health-filter" className="input w-32" value={health} onChange={(event) => setHealth(event.target.value)}>
              <option value="">All</option>
              <option value="healthy">healthy</option>
              <option value="warning">warning</option>
              <option value="critical">critical</option>
              <option value="offline">offline</option>
            </select>
          </div>
          <button type="button" className="btn btn-secondary" onClick={fleet.reload} disabled={fleet.loading}>
            <Icon name="refresh" size={13} /> Refresh
          </button>
        </div>
      </Card>

      <Card bodyClassName="" footer={`${rows.length} of ${fleet.data?.length ?? 0} instances · updated ${fleet.updatedAt ? timeAgo(fleet.updatedAt.toISOString()) : '—'}`}>
        {fleet.loading && !fleet.data ? (
          <div className="p-4"><Loading rows={5} /></div>
        ) : fleet.error ? (
          <div className="p-4"><ErrorState message={fleet.error} onRetry={fleet.reload} /></div>
        ) : rows.length === 0 ? (
          <EmptyState
            title="No instances match these filters"
            description="Adjust the filters, or register a simulated instance to explore the platform."
            icon="server"
            action={canOperate ? <button className="btn btn-secondary mt-2" onClick={() => setCreateOpen(true)}>Add instance</button> : undefined}
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="table">
              <thead>
                <tr>
                  <th>Instance</th>
                  <th>Source</th>
                  <th>Type</th>
                  <th>Environment</th>
                  <th>Health</th>
                  <th>CPU</th>
                  <th>Memory</th>
                  <th>Disk</th>
                  <th>Est. cost</th>
                  <th className="text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(({ instance, cpu_percent, memory_percent, disk_percent }) => (
                  <tr key={instance.id}>
                    <td>
                      <Link to={`/instances/${instance.id}`} className="font-medium text-brand-600 hover:underline dark:text-brand-400">
                        {instance.name}
                      </Link>
                      <p className="mt-0.5 text-[11px] text-slate-500">
                        {instance.hostname ?? instance.external_id ?? '—'} · {instance.region}
                      </p>
                    </td>
                    <td><SourceBadge source={instance.source} /></td>
                    <td className="whitespace-nowrap text-xs">{instance.instance_type}</td>
                    <td className="text-xs">{instance.environment}</td>
                    <td><HealthBadge value={instance.health_status} /></td>
                    <td><UsageBar value={cpu_percent} /></td>
                    <td><UsageBar value={memory_percent} /></td>
                    <td><UsageBar value={disk_percent} /></td>
                    <td className="whitespace-nowrap text-xs">{instance.monthly_cost_usd ? formatMoney(instance.monthly_cost_usd) : '—'}</td>
                    <td>
                      <div className="flex items-center justify-end gap-1">
                        <Link to={`/instances/${instance.id}`} className="btn btn-ghost btn-xs" title="View details">
                          <Icon name="eye" size={13} />
                        </Link>
                        {canOperate && instance.source === 'simulated' && (
                          <>
                            {instance.status === 'running' ? (
                              <button type="button" className="btn btn-ghost btn-xs" title="Stop (simulated)" onClick={() => power(instance.id, 'stop', instance.name)}>
                                <Icon name="stop" size={12} />
                              </button>
                            ) : (
                              <button type="button" className="btn btn-ghost btn-xs" title="Start (simulated)" onClick={() => power(instance.id, 'start', instance.name)}>
                                <Icon name="play" size={12} />
                              </button>
                            )}
                            <button type="button" className="btn btn-ghost btn-xs text-rose-500" title="Remove simulated row" onClick={() => remove(instance.id, instance.name)}>
                              <Icon name="trash" size={12} />
                            </button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <DataNote>
        Local rows are real measurements of this machine via psutil. Simulated rows are synthetic and never represent a real
        server. AWS rows only appear after a read-only account is connected; otherwise the AWS inventory stays in simulation mode.
      </DataNote>

      <Modal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title="Add simulated instance"
        subtitle="Creates a synthetic inventory row with generated telemetry. No cloud resource is provisioned."
        footer={
          <>
            <button type="button" className="btn btn-secondary" onClick={() => setCreateOpen(false)}>Cancel</button>
            <button type="submit" form="create-instance" className="btn btn-primary" disabled={saving}>
              {saving ? 'Creating…' : 'Create instance'}
            </button>
          </>
        }
      >
        <form id="create-instance" onSubmit={submitCreate} className="grid gap-3 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <Field label="Name">
              <input required minLength={2} className="input" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} placeholder="staging-worker-02" />
            </Field>
          </div>
          <Field label="Instance type">
            <select className="input" value={form.instance_type} onChange={(event) => setForm({ ...form, instance_type: event.target.value })}>
              {(pricing.data ?? [{ instance_type: 't3.medium', hourly_usd: 0.0416 }]).map((row) => (
                <option key={row.instance_type} value={row.instance_type}>
                  {row.instance_type} — ${row.hourly_usd}/h
                </option>
              ))}
            </select>
          </Field>
          <Field label="Environment">
            <select className="input" value={form.environment} onChange={(event) => setForm({ ...form, environment: event.target.value })}>
              <option value="development">development</option>
              <option value="staging">staging</option>
              <option value="production">production</option>
            </select>
          </Field>
          <Field label="Region">
            <select className="input" value={form.region} onChange={(event) => setForm({ ...form, region: event.target.value })}>
              {['us-east-1', 'us-west-2', 'eu-west-1', 'ap-south-1'].map((region) => (
                <option key={region} value={region}>{region}</option>
              ))}
            </select>
          </Field>
          <Field label="Workload role" hint="Drives the simulated utilisation profile.">
            <select className="input" value={form.role} onChange={(event) => setForm({ ...form, role: event.target.value })}>
              {['web', 'api', 'worker', 'database', 'cache', 'bastion'].map((role) => (
                <option key={role} value={role}>{role}</option>
              ))}
            </select>
          </Field>
          <Field label="vCPU">
            <input type="number" min={1} max={64} className="input" value={form.cpu_cores} onChange={(event) => setForm({ ...form, cpu_cores: Number(event.target.value) })} />
          </Field>
          <Field label="Memory (MB)">
            <input type="number" min={512} step={512} className="input" value={form.memory_mb} onChange={(event) => setForm({ ...form, memory_mb: Number(event.target.value) })} />
          </Field>
          <Field label="Disk (GB)">
            <input type="number" min={8} className="input" value={form.disk_gb} onChange={(event) => setForm({ ...form, disk_gb: Number(event.target.value) })} />
          </Field>
          <p className="sm:col-span-2 text-[11px] text-slate-500">
            Estimated cost is recalculated from the stored pricing model: compute hours × hourly rate, plus EBS per GB.
          </p>
        </form>
      </Modal>
    </div>
  )
}
