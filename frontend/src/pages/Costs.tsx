import { useState } from 'react'
import { Link } from 'react-router-dom'
import { costApi } from '../api/endpoints'
import { useApi } from '../hooks/useApi'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../context/ToastContext'
import { BarSeries } from '../components/Charts'
import { Card, DataNote, EmptyState, ErrorState, Field, Loading, Modal, PageHeader, Progress, StatCard } from '../components/ui'
import { Icon } from '../components/Icon'
import { errorMessage } from '../api/client'
import { formatMoney, formatNumber, formatPercent } from '../lib/format'
import type { CostRecommendation, PricingRow } from '../types'

const TYPE_LABEL: Record<string, string> = {
  idle: 'Idle resource',
  oversized: 'Right-size',
  unattached_storage: 'Storage',
  commitment: 'Commitment',
  scheduling: 'Scheduling',
}

export default function Costs() {
  const { isAdmin, canOperate } = useAuth()
  const toast = useToast()
  const [budgetOpen, setBudgetOpen] = useState(false)
  const [budgetValue, setBudgetValue] = useState(0)
  const [pricingDraft, setPricingDraft] = useState<Record<string, { hourly_usd: number; ebs_gb_usd: number }>>({})

  const summary = useApi(() => costApi.summary(), [])
  const trend = useApi(() => costApi.trend(), [])
  const recommendations = useApi(() => costApi.recommendations(), [])
  const pricing = useApi(() => costApi.pricing(), [])

  async function saveBudget(event: React.FormEvent) {
    event.preventDefault()
    try {
      await costApi.setBudget(budgetValue)
      toast.success('Budget updated')
      setBudgetOpen(false)
      summary.reload()
    } catch (err) {
      toast.error(errorMessage(err))
    }
  }

  async function savePricing(row: PricingRow) {
    const draft = pricingDraft[row.instance_type]
    if (!draft) return
    try {
      await costApi.updatePricing(row.instance_type, draft)
      toast.success(`Pricing for ${row.instance_type} updated`)
      setPricingDraft((current) => {
        const next = { ...current }
        delete next[row.instance_type]
        return next
      })
      pricing.reload()
      summary.reload()
      recommendations.reload()
    } catch (err) {
      toast.error(errorMessage(err))
    }
  }

  async function snapshot() {
    try {
      const result = await costApi.snapshot()
      toast.success(`Stored estimate snapshot for ${result.period} (${formatMoney(result.total_usd)})`)
      trend.reload()
      summary.reload()
    } catch (err) {
      toast.error(errorMessage(err))
    }
  }

  if (summary.loading && !summary.data) {
    return <div><PageHeader title="Cost optimization" /><Loading rows={6} /></div>
  }
  if (summary.error || !summary.data) {
    return <div><PageHeader title="Cost optimization" /><ErrorState message={summary.error ?? 'Unavailable'} onRetry={summary.reload} /></div>
  }

  const data = summary.data
  const budgetTone = data.budget_used_percent >= 100 ? 'critical' : data.budget_used_percent >= 80 ? 'warning' : 'success'

  return (
    <div className="space-y-4">
      <PageHeader
        title="Cost optimization"
        subtitle="Estimates derived from the editable pricing model and observed utilisation. Not an AWS invoice."
        badge={<span className="badge badge-medium">estimated</span>}
        actions={
          <>
            <button type="button" className="btn btn-secondary" onClick={snapshot} disabled={!canOperate}>
              <Icon name="database" size={13} /> Store snapshot
            </button>
            {isAdmin && (
              <button type="button" className="btn btn-primary" onClick={() => { setBudgetValue(data.budget_usd); setBudgetOpen(true) }}>
                <Icon name="settings" size={13} /> Edit budget
              </button>
            )}
          </>
        }
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <StatCard label="Estimated / month" value={formatMoney(data.estimated_monthly_usd, data.currency)} hint={`${data.instance_count} resources modelled`} icon="dollar" tone="info" />
        <StatCard label="Month to date" value={formatMoney(data.month_to_date_usd, data.currency)} hint={`Period ${data.period}`} icon="clock" tone="default" />
        <StatCard label="Forecast" value={formatMoney(data.forecast_usd, data.currency)} hint={`${data.change_percent >= 0 ? '+' : ''}${data.change_percent}% vs last month`} icon="activity" tone={data.change_percent > 5 ? 'warning' : 'success'} />
        <StatCard label="Budget" value={formatMoney(data.budget_usd, data.currency)} hint={`${formatPercent(data.budget_used_percent, 0)} used`} icon="shield" tone={budgetTone === 'critical' ? 'critical' : budgetTone === 'warning' ? 'warning' : 'success'} />
        <StatCard label="Potential savings" value={formatMoney(data.potential_savings_usd, data.currency)} hint={`${recommendations.data?.length ?? 0} recommendations`} icon="wrench" tone="success" />
        <StatCard label="Idle resources" value={data.idle_instance_count} hint="Average CPU under idle threshold" icon="server" tone={data.idle_instance_count ? 'warning' : 'success'} />
      </div>

      <Card title="Budget utilisation" subtitle={`${formatMoney(data.estimated_monthly_usd, data.currency)} of ${formatMoney(data.budget_usd, data.currency)} monthly budget`}>
        <Progress value={data.budget_used_percent} tone={budgetTone} />
        <div className="mt-2 flex items-center justify-between text-[11.5px] text-slate-500">
          <span>{formatPercent(data.budget_used_percent, 1)} consumed by the current estimate</span>
          <span>{data.budget_used_percent >= 100 ? 'Over budget' : `${formatMoney(Math.max(data.budget_usd - data.estimated_monthly_usd, 0), data.currency)} headroom`}</span>
        </div>
      </Card>

      <div className="grid gap-4 xl:grid-cols-3">
        <Card title="Cost trend" subtitle="Estimated monthly spend by period" className="xl:col-span-2">
          {trend.loading && !trend.data ? (
            <Loading rows={4} />
          ) : !trend.data || trend.data.length === 0 ? (
            <EmptyState title="No history yet" description="Store a snapshot to build the trend." icon="dollar" />
          ) : (
            <BarSeries
              data={trend.data.map((point) => ({ period: point.period, estimated: point.estimated_usd, actual: point.actual_usd ?? 0 }))}
              xKey="period"
              height={250}
              series={[
                { key: 'estimated', label: 'Estimated', color: '#3186fb' },
                { key: 'actual', label: 'Actual (billing)', color: '#10b981' },
              ]}
            />
          )}
          <DataNote>Actual billing only appears when cost records are imported from an authorised AWS source. This build ships estimates only.</DataNote>
        </Card>

        <Card title="Spend by resource" subtitle="Largest estimated monthly costs" bodyClassName="">
          <div className="max-h-[330px] overflow-y-auto">
            <table className="table">
              <thead>
                <tr><th>Resource</th><th>Type</th><th className="text-right">Monthly</th></tr>
              </thead>
              <tbody>
                {data.breakdown.slice(0, 10).map((row) => (
                  <tr key={row.instance_id}>
                    <td>
                      <Link to={`/instances/${row.instance_id}`} className="text-[12.5px] font-medium text-brand-600 hover:underline dark:text-brand-400">{row.name}</Link>
                      <p className="text-[10.5px] text-slate-500">{row.environment} · {row.source}</p>
                    </td>
                    <td className="text-[11px]">{row.type}</td>
                    <td className="text-right text-[12px] tabular-nums">{formatMoney(row.monthly_usd, data.currency)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      <Card title="Optimization recommendations" subtitle="Generated from observed utilisation and the pricing model" bodyClassName="divide-y">
        {recommendations.loading && !recommendations.data ? (
          <div className="p-4"><Loading rows={4} /></div>
        ) : (recommendations.data ?? []).length === 0 ? (
          <EmptyState title="No recommendations" description="No idle or oversized resources were detected from the available telemetry." icon="check" />
        ) : (
          recommendations.data!.map((rec: CostRecommendation) => (
            <div key={rec.id} className="flex flex-col gap-2 px-5 py-3 sm:flex-row sm:items-start sm:justify-between">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="badge badge-info">{TYPE_LABEL[rec.type] ?? rec.type}</span>
                  <span className="text-[13px] font-medium text-slate-800 dark:text-slate-100">{rec.title}</span>
                  <span className={`badge ${rec.confidence === 'high' ? 'badge-success' : rec.confidence === 'medium' ? 'badge-medium' : 'badge-neutral'}`}>
                    {rec.confidence} confidence
                  </span>
                </div>
                <p className="mt-1 max-w-3xl text-[12px] leading-relaxed text-slate-600 dark:text-slate-300">{rec.description}</p>
                <p className="mt-1 text-[11px] text-slate-500">{rec.action}</p>
                <pre className="mt-1.5 hidden rounded bg-slate-100 p-2 font-mono text-[10px] text-slate-500 dark:bg-slate-950/60 sm:block">
                  {JSON.stringify(rec.evidence)}
                </pre>
              </div>
              <div className="shrink-0 text-right">
                <p className="text-base font-semibold text-emerald-600 dark:text-emerald-400">{formatMoney(rec.monthly_savings_usd, data.currency)}<span className="text-[11px] font-normal text-slate-500">/mo</span></p>
                <p className="text-[10.5px] text-slate-500">{formatMoney(rec.current_monthly_usd, data.currency)} → {formatMoney(rec.projected_monthly_usd, data.currency)}</p>
              </div>
            </div>
          ))
        )}
      </Card>

      <Card
        title="Pricing assumptions"
        subtitle="Edit the hourly rate used for estimates. Changes affect future calculations only."
        bodyClassName=""
        footer="These are modelled on-demand prices for estimation, not live AWS rates. Replace them with your negotiated pricing for accurate forecasts."
      >
        <div className="overflow-x-auto">
          <table className="table">
            <thead>
              <tr>
                <th>Instance type</th>
                <th>vCPU</th>
                <th>Memory</th>
                <th>Hourly (USD)</th>
                <th>EBS / GB</th>
                <th className="text-right">Save</th>
              </tr>
            </thead>
            <tbody>
              {(pricing.data ?? []).map((row) => {
                const draft = pricingDraft[row.instance_type] ?? { hourly_usd: row.hourly_usd, ebs_gb_usd: row.ebs_gb_usd }
                const dirty = Boolean(pricingDraft[row.instance_type])
                return (
                  <tr key={row.instance_type}>
                    <td className="font-mono text-[11.5px]">{row.instance_type}</td>
                    <td className="text-xs">{row.vcpu}</td>
                    <td className="text-xs">{row.memory_gb} GB</td>
                    <td>
                      <input
                        type="number"
                        step="0.0001"
                        min={0}
                        className="input w-24 py-1 text-xs"
                        value={draft.hourly_usd}
                        disabled={!isAdmin}
                        onChange={(event) => setPricingDraft({ ...pricingDraft, [row.instance_type]: { ...draft, hourly_usd: Number(event.target.value) } })}
                      />
                    </td>
                    <td>
                      <input
                        type="number"
                        step="0.001"
                        min={0}
                        className="input w-20 py-1 text-xs"
                        value={draft.ebs_gb_usd}
                        disabled={!isAdmin}
                        onChange={(event) => setPricingDraft({ ...pricingDraft, [row.instance_type]: { ...draft, ebs_gb_usd: Number(event.target.value) } })}
                      />
                    </td>
                    <td className="text-right">
                      <button type="button" className="btn btn-secondary btn-xs" disabled={!isAdmin || !dirty} onClick={() => savePricing(row)}>
                        Save
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </Card>

      <DataNote>
        Estimates use {formatNumber(730, 0)} hours/month and the pricing rows above. Idle detection requires at least three
        telemetry samples; simulated instances therefore produce simulated recommendations. No resource is ever terminated,
        resized or stopped automatically — every action is manual and audited.
      </DataNote>

      <Modal
        open={budgetOpen}
        onClose={() => setBudgetOpen(false)}
        title="Monthly budget"
        subtitle="Used for the budget utilisation card. Evaluation only; no billing alert is sent."
        footer={
          <>
            <button type="button" className="btn btn-secondary" onClick={() => setBudgetOpen(false)}>Cancel</button>
            <button type="submit" form="budget-form" className="btn btn-primary">Save budget</button>
          </>
        }
      >
        <form id="budget-form" onSubmit={saveBudget}>
          <Field label="Budget (USD per month)">
            <input type="number" min={1} step="1" className="input" value={budgetValue} onChange={(event) => setBudgetValue(Number(event.target.value))} />
          </Field>
        </form>
      </Modal>
    </div>
  )
}
