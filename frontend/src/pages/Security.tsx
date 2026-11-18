import { Fragment, useState } from 'react'
import { securityApi } from '../api/endpoints'
import { API_BASE_URL, TOKEN_KEY, errorMessage } from '../api/client'
import { useApi } from '../hooks/useApi'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../context/ToastContext'
import { Card, DataNote, EmptyState, ErrorState, Loading, PageHeader, Pagination, SeverityBadge, SourceBadge, StatCard } from '../components/ui'
import { Icon, Spinner } from '../components/Icon'
import { Donut } from '../components/Charts'
import { formatDateTime, timeAgo, truncate } from '../lib/format'
import type { Finding, ScanResult } from '../types'

const TOOL_OPTIONS = [
  { id: 'rules', label: 'IaC rules', hint: 'Terraform + Dockerfile policy checks (built in)' },
  { id: 'aws', label: 'AWS config audit', hint: 'S3, security groups, IAM inventory' },
  { id: 'bandit', label: 'Bandit', hint: 'Python static analysis' },
  { id: 'pip-audit', label: 'pip-audit', hint: 'Dependency advisories (network)' },
  { id: 'checkov', label: 'Checkov', hint: 'Terraform/Kubernetes policy' },
  { id: 'trivy', label: 'Trivy', hint: 'Container and filesystem scanning' },
]

export default function Security() {
  const { canOperate } = useAuth()
  const toast = useToast()
  const [page, setPage] = useState(1)
  const [severity, setSeverity] = useState('')
  const [status, setStatus] = useState('open')
  const [category, setCategory] = useState('')
  const [search, setSearch] = useState('')
  const [expanded, setExpanded] = useState<number | null>(null)
  const [scanOpen, setScanOpen] = useState(false)
  const [tools, setTools] = useState<string[]>(['rules', 'aws', 'bandit'])
  const [scanning, setScanning] = useState(false)
  const [scanResult, setScanResult] = useState<ScanResult | null>(null)
  const [scanRequested, setScanRequested] = useState<string[]>([])

  const summary = useApi(() => securityApi.summary(), [])
  const toolsInfo = useApi(() => securityApi.tools(), [])
  const findings = useApi(
    () => securityApi.findings({ page, page_size: 15, severity: severity || undefined, status, category: category || undefined, search: search || undefined }),
    [page, severity, status, category, search],
  )

  async function runScan() {
    const requested = [...tools]
    setScanRequested(requested)
    setScanning(true)
    setScanResult(null)
    try {
      const result = await securityApi.scan({ tools: requested, include_cloud: requested.includes('aws') })
      setScanResult(result)
      toast.success(`Scan complete: ${result.findings_created} new, ${result.findings_updated} updated`)
      summary.reload()
      findings.reload()
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setScanning(false)
    }
  }

  async function setFindingStatus(finding: Finding, next: string) {
    try {
      await securityApi.setStatus(finding.id, next)
      toast.success(`${finding.title} marked ${next.replace('_', ' ')}`)
      findings.reload()
      summary.reload()
    } catch (err) {
      toast.error(errorMessage(err))
    }
  }

  async function download(format: 'json' | 'csv') {
    try {
      const token = localStorage.getItem(TOKEN_KEY)
      const response = await fetch(`${API_BASE_URL}${securityApi.reportUrl(format)}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      })
      if (!response.ok) throw new Error(`Report request failed (${response.status})`)
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `cloudops-sentinel-findings.${format}`
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(url)
      toast.success(`Downloaded ${format.toUpperCase()} report`)
    } catch (err) {
      toast.error(errorMessage(err))
    }
  }

  const counts = summary.data?.counts ?? {}
  const donutData = [
    { name: 'Critical', value: counts.critical ?? 0, color: '#f43f5e' },
    { name: 'High', value: counts.high ?? 0, color: '#f97316' },
    { name: 'Medium', value: counts.medium ?? 0, color: '#f59e0b' },
    { name: 'Low', value: counts.low ?? 0, color: '#0ea5e9' },
  ].filter((item) => item.value > 0)

  return (
    <div className="space-y-4">
      <PageHeader
        title="Security findings"
        subtitle="Configuration, code, dependency and container checks. Every finding records how it was produced."
        actions={
          <>
            <button type="button" className="btn btn-secondary" onClick={() => download('json')}>
              <Icon name="download" size={13} /> JSON
            </button>
            <button type="button" className="btn btn-secondary" onClick={() => download('csv')}>
              <Icon name="download" size={13} /> CSV
            </button>
            <button type="button" className="btn btn-primary" onClick={() => setScanOpen((open) => !open)} disabled={!canOperate}>
              <Icon name="shield" size={13} /> Run scan
            </button>
          </>
        }
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-5">
        <StatCard label="Risk score" value={summary.data?.risk_score ?? '—'} hint={summary.data ? `${summary.data.risk_level} risk` : ''} icon="shield" tone={summary.data && summary.data.risk_score >= 40 ? 'critical' : 'warning'} />
        <StatCard label="Critical" value={counts.critical ?? 0} icon="alert" tone="critical" />
        <StatCard label="High" value={counts.high ?? 0} icon="alert" tone="warning" />
        <StatCard label="Open findings" value={summary.data?.total ?? 0} hint={`${summary.data?.findings_total ?? 0} total tracked`} icon="list" tone="info" />
        <StatCard label="Last scan" value={summary.data?.last_scan_at ? timeAgo(summary.data.last_scan_at) : 'never'} hint={summary.data?.last_scan_at ? formatDateTime(summary.data.last_scan_at) : 'Run a scan to populate findings'} icon="clock" tone="default" />
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Card title="Severity distribution" subtitle="Open findings only">
          {donutData.length === 0 ? (
            <EmptyState title="No open findings" description="Run a scan to evaluate the current configuration." icon="shield" />
          ) : (
            <>
              <Donut data={donutData} centerLabel="open" centerValue={String(summary.data?.total ?? 0)} />
              <div className="mt-2 grid grid-cols-2 gap-1.5 text-[11.5px]">
                {donutData.map((item) => (
                  <span key={item.name} className="flex items-center gap-1.5 text-slate-600 dark:text-slate-300">
                    <span className="h-2 w-2 rounded-full" style={{ backgroundColor: item.color }} /> {item.name}: {item.value}
                  </span>
                ))}
              </div>
            </>
          )}
        </Card>

        <Card title="Scanner availability" subtitle="Missing tools are reported as skipped, never simulated." className="xl:col-span-2">
          {toolsInfo.loading && !toolsInfo.data ? (
            <Loading rows={4} />
          ) : (
            <div className="grid gap-2 sm:grid-cols-2">
              {(toolsInfo.data?.tools ?? []).map((tool) => (
                <div key={tool.name} className="flex items-start justify-between gap-2 rounded-lg border px-3 py-2">
                  <div>
                    <p className="text-[12.5px] font-medium text-slate-800 dark:text-slate-100">{tool.name}</p>
                    <p className="text-[11px] text-slate-500">{tool.purpose}</p>
                  </div>
                  <span className={`badge ${tool.available ? 'badge-success' : 'badge-neutral'}`}>
                    {tool.available ? 'available' : 'not installed'}
                  </span>
                </div>
              ))}
            </div>
          )}
          <DataNote>{toolsInfo.data?.note ?? 'Tool availability is probed at request time.'}</DataNote>
        </Card>
      </div>

      {scanOpen && (
        <Card title="Run a security scan" subtitle="Select which scanners to execute. Results are stored with the tool name and timestamp.">
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {TOOL_OPTIONS.map((tool) => {
              const info = toolsInfo.data?.tools.find((item) => item.name === tool.id)
              const available = tool.id === 'rules' || tool.id === 'aws' ? true : info?.available
              return (
                <label key={tool.id} className={`flex items-start gap-2 rounded-lg border px-3 py-2 ${available ? '' : 'opacity-60'}`}>
                  <input
                    type="checkbox"
                    className="mt-0.5 h-3.5 w-3.5"
                    checked={tools.includes(tool.id)}
                    disabled={!available}
                    onChange={(event) =>
                      setTools((current) => (event.target.checked ? [...current, tool.id] : current.filter((item) => item !== tool.id)))
                    }
                  />
                  <span>
                    <span className="block text-[12.5px] font-medium text-slate-800 dark:text-slate-100">{tool.label}</span>
                    <span className="block text-[11px] text-slate-500">{tool.hint}</span>
                  </span>
                </label>
              )
            })}
          </div>
          <div className="mt-3 flex items-center gap-2">
            <button type="button" className="btn btn-primary" onClick={runScan} disabled={scanning || tools.length === 0}>
              {scanning ? <Spinner size={13} /> : <Icon name="play" size={12} />} {scanning ? 'Scanning…' : 'Start scan'}
            </button>
            <button type="button" className="btn btn-secondary" onClick={() => setScanOpen(false)}>Close</button>
            {scanning && <span className="text-[11px] text-slate-500">External scanners can take up to a minute.</span>}
          </div>

          {scanResult && (
            <div className="mt-3 rounded-lg border bg-slate-50 p-3 dark:bg-slate-950/50">
              <p className="text-[12px] font-medium text-slate-800 dark:text-slate-100">
                Scan {scanResult.scan_id} · {scanResult.findings_created} created, {scanResult.findings_updated} updated,{' '}
                {scanResult.findings_resolved} resolved
              </p>
              <p className="mt-0.5 text-[11px] text-slate-500">
                Requested: {scanRequested.join(', ') || 'none'} · executed/skipped: {scanResult.tools.map((tool) => tool.tool).join(', ')}
              </p>
              <div className="mt-2 space-y-1">
                {scanResult.tools.map((tool) => (
                  <div key={tool.tool} className="flex items-center justify-between text-[11.5px]">
                    <span className="font-mono text-slate-600 dark:text-slate-300">{tool.tool}</span>
                    <span className="flex items-center gap-2">
                      <span className={`badge ${tool.status === 'executed' ? 'badge-success' : tool.status === 'skipped' ? 'badge-neutral' : 'badge-critical'}`}>{tool.status}</span>
                      <span className="text-slate-500">{tool.findings} findings · {tool.duration_ms} ms</span>
                    </span>
                  </div>
                ))}
              </div>
              {scanResult.simulated_resources && (
                <p className="mt-2 text-[11px] text-amber-600 dark:text-amber-400">
                  AWS findings were derived from the simulated inventory because no AWS account is connected.
                </p>
              )}
            </div>
          )}
        </Card>
      )}

      <Card bodyClassName="">
        <div className="flex flex-wrap items-end gap-2 border-b px-4 py-3">
          <div className="min-w-[200px] flex-1">
            <label className="label" htmlFor="finding-search">Search</label>
            <input id="finding-search" className="input" placeholder="Title, resource or description" value={search} onChange={(event) => { setSearch(event.target.value); setPage(1) }} />
          </div>
          <div>
            <label className="label" htmlFor="finding-severity">Severity</label>
            <select id="finding-severity" className="input w-32" value={severity} onChange={(event) => { setSeverity(event.target.value); setPage(1) }}>
              <option value="">All</option>
              <option value="critical">critical</option>
              <option value="high">high</option>
              <option value="medium">medium</option>
              <option value="low">low</option>
            </select>
          </div>
          <div>
            <label className="label" htmlFor="finding-status">Status</label>
            <select id="finding-status" className="input w-32" value={status} onChange={(event) => { setStatus(event.target.value); setPage(1) }}>
              <option value="open">open</option>
              <option value="acknowledged">acknowledged</option>
              <option value="resolved">resolved</option>
              <option value="false_positive">false positive</option>
              <option value="all">all</option>
            </select>
          </div>
          <div>
            <label className="label" htmlFor="finding-category">Category</label>
            <select id="finding-category" className="input w-36" value={category} onChange={(event) => { setCategory(event.target.value); setPage(1) }}>
              <option value="">All</option>
              {(summary.data?.categories ?? []).map((item) => (
                <option key={item.category} value={item.category}>{item.category}</option>
              ))}
            </select>
          </div>
        </div>

        {findings.loading && !findings.data ? (
          <div className="p-4"><Loading rows={6} /></div>
        ) : findings.error ? (
          <div className="p-4"><ErrorState message={findings.error} onRetry={findings.reload} /></div>
        ) : findings.data?.items.length === 0 ? (
          <EmptyState title="No findings match these filters" description="Try widening the status filter or run a new scan." icon="shield" />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="table">
                <thead>
                  <tr>
                    <th>Finding</th>
                    <th>Severity</th>
                    <th>Resource</th>
                    <th>Source</th>
                    <th>Status</th>
                    <th>Last seen</th>
                    <th className="text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {(findings.data?.items ?? []).map((finding) => (
                    <Fragment key={finding.id}>
                      <tr>
                        <td>
                          <button type="button" className="text-left text-[12.5px] font-medium text-slate-800 hover:text-brand-600 dark:text-slate-100" onClick={() => setExpanded(expanded === finding.id ? null : finding.id)}>
                            {finding.title}
                          </button>
                          <p className="mt-0.5 text-[11px] text-slate-500">{truncate(finding.description, 84)}</p>
                        </td>
                        <td><SeverityBadge value={finding.severity} /></td>
                        <td className="max-w-[180px]">
                          <span className="block truncate font-mono text-[11px] text-slate-600 dark:text-slate-300">{finding.resource_name}</span>
                          <span className="text-[10px] uppercase tracking-wide text-slate-400">{finding.resource_type}</span>
                        </td>
                        <td>
                          <SourceBadge source={finding.source_kind} />
                          <p className="mt-0.5 font-mono text-[10px] text-slate-400">{finding.scan_source}</p>
                        </td>
                        <td><span className="badge badge-neutral">{finding.status.replace('_', ' ')}</span></td>
                        <td className="whitespace-nowrap text-[11px] text-slate-500">{timeAgo(finding.last_seen_at)}</td>
                        <td>
                          <div className="flex items-center justify-end gap-1">
                            <button type="button" className="btn btn-ghost btn-xs" onClick={() => setExpanded(expanded === finding.id ? null : finding.id)}>
                              <Icon name="eye" size={13} />
                            </button>
                            {canOperate && finding.status === 'open' && (
                              <button type="button" className="btn btn-secondary btn-xs" onClick={() => setFindingStatus(finding, 'acknowledged')}>
                                Acknowledge
                              </button>
                            )}
                            {canOperate && finding.status !== 'resolved' && (
                              <button type="button" className="btn btn-secondary btn-xs" onClick={() => setFindingStatus(finding, 'resolved')}>
                                Resolve
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                      {expanded === finding.id && (
                        <tr className="bg-slate-50 dark:bg-slate-950/40">
                          <td colSpan={7} className="px-4 py-4">
                            <div className="grid gap-4 lg:grid-cols-2">
                              <div>
                                <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Description</p>
                                <p className="mt-1 text-[12.5px] leading-relaxed text-slate-700 dark:text-slate-200">{finding.description}</p>
                                <p className="mt-3 text-[11px] font-semibold uppercase tracking-wide text-slate-500">Evidence</p>
                                <pre className="code-block mt-1 whitespace-pre-wrap">{finding.evidence || '—'}</pre>
                              </div>
                              <div>
                                <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Remediation</p>
                                <p className="mt-1 text-[12.5px] leading-relaxed text-slate-700 dark:text-slate-200">{finding.remediation}</p>
                                <dl className="mt-3 grid grid-cols-2 gap-2 text-[11.5px]">
                                  <div><dt className="text-slate-500">Finding key</dt><dd className="font-mono text-[10.5px]">{finding.finding_key}</dd></div>
                                  <div><dt className="text-slate-500">Scan ID</dt><dd className="font-mono text-[10.5px]">{finding.scan_id ?? '—'}</dd></div>
                                  <div><dt className="text-slate-500">First seen</dt><dd>{formatDateTime(finding.first_seen_at)}</dd></div>
                                  <div><dt className="text-slate-500">Last seen</dt><dd>{formatDateTime(finding.last_seen_at)}</dd></div>
                                </dl>
                                {canOperate && (
                                  <button type="button" className="btn btn-secondary btn-xs mt-3" onClick={() => setFindingStatus(finding, 'false_positive')}>
                                    Mark as false positive
                                  </button>
                                )}
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="px-4 pb-3">
              <Pagination page={findings.data?.page ?? 1} pages={findings.data?.pages ?? 1} total={findings.data?.total ?? 0} onPage={setPage} />
            </div>
          </>
        )}
      </Card>

      <DataNote>
        Findings keep the provenance of their source: <span className="font-medium">simulated</span> (derived from the built-in
        simulated AWS inventory), <span className="font-medium">aws</span> (read from a connected account),{' '}
        <span className="font-medium">tool</span> (real scanner output) or <span className="font-medium">rule-engine</span>{' '}
        (built-in policy checks over files in this repository). No finding is invented for a tool that did not run.
      </DataNote>
    </div>
  )
}
