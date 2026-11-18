import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { chartColors } from '../lib/format'

export interface Series {
  key: string
  label: string
  color: string
  unit?: string
}

const tooltipStyle = {
  backgroundColor: 'rgba(15, 23, 42, 0.94)',
  border: '1px solid rgba(148, 163, 184, 0.3)',
  borderRadius: 8,
  fontSize: 12,
  color: '#e2e8f0',
  padding: '6px 10px',
}

export function AreaTrend({
  data,
  xKey,
  series,
  height = 240,
  tickFormatter,
  unit = '%',
  domain,
}: {
  data: Record<string, unknown>[]
  xKey: string
  series: Series[]
  height?: number
  tickFormatter?: (value: string) => string
  unit?: string
  domain?: [number, number]
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 8, right: 12, left: -18, bottom: 0 }}>
        <defs>
          {series.map((item) => (
            <linearGradient key={item.key} id={`grad-${item.key}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={item.color} stopOpacity={0.35} />
              <stop offset="95%" stopColor={item.color} stopOpacity={0.02} />
            </linearGradient>
          ))}
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke={chartColors.grid} vertical={false} />
        <XAxis
          dataKey={xKey}
          tick={{ fontSize: 10, fill: chartColors.text }}
          tickFormatter={tickFormatter}
          minTickGap={28}
          axisLine={false}
          tickLine={false}
        />
        <YAxis
          tick={{ fontSize: 10, fill: chartColors.text }}
          domain={domain}
          axisLine={false}
          tickLine={false}
          width={40}
        />
        <Tooltip
          contentStyle={tooltipStyle}
          labelFormatter={(value) => (tickFormatter ? tickFormatter(String(value)) : String(value))}
          formatter={(value: number, name: string) => [`${Number(value).toFixed(1)}${unit}`, name]}
        />
        <Legend wrapperStyle={{ fontSize: 11 }} iconType="circle" iconSize={7} />
        {series.map((item) => (
          <Area
            key={item.key}
            type="monotone"
            dataKey={item.key}
            name={item.label}
            stroke={item.color}
            strokeWidth={1.8}
            fill={`url(#grad-${item.key})`}
            dot={false}
            isAnimationActive={false}
          />
        ))}
      </AreaChart>
    </ResponsiveContainer>
  )
}

export function BarSeries({
  data,
  xKey,
  series,
  height = 240,
  tickFormatter,
}: {
  data: Record<string, unknown>[]
  xKey: string
  series: Series[]
  height?: number
  tickFormatter?: (value: string) => string
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 12, left: -18, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={chartColors.grid} vertical={false} />
        <XAxis dataKey={xKey} tick={{ fontSize: 10, fill: chartColors.text }} tickFormatter={tickFormatter} axisLine={false} tickLine={false} />
        <YAxis tick={{ fontSize: 10, fill: chartColors.text }} axisLine={false} tickLine={false} width={46} />
        <Tooltip contentStyle={tooltipStyle} cursor={{ fill: 'rgba(148,163,184,0.08)' }} />
        <Legend wrapperStyle={{ fontSize: 11 }} iconType="circle" iconSize={7} />
        {series.map((item) => (
          <Bar key={item.key} dataKey={item.key} name={item.label} fill={item.color} radius={[3, 3, 0, 0]} maxBarSize={34} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  )
}

export function LineTrend({
  data,
  xKey,
  series,
  height = 220,
  tickFormatter,
}: {
  data: Record<string, unknown>[]
  xKey: string
  series: Series[]
  height?: number
  tickFormatter?: (value: string) => string
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 12, left: -18, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={chartColors.grid} vertical={false} />
        <XAxis dataKey={xKey} tick={{ fontSize: 10, fill: chartColors.text }} tickFormatter={tickFormatter} axisLine={false} tickLine={false} />
        <YAxis tick={{ fontSize: 10, fill: chartColors.text }} axisLine={false} tickLine={false} width={46} />
        <Tooltip contentStyle={tooltipStyle} />
        <Legend wrapperStyle={{ fontSize: 11 }} iconType="circle" iconSize={7} />
        {series.map((item) => (
          <Line
            key={item.key}
            type="monotone"
            dataKey={item.key}
            name={item.label}
            stroke={item.color}
            strokeWidth={1.8}
            dot={false}
            isAnimationActive={false}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  )
}

export function Donut({
  data,
  height = 220,
  innerRadius = 52,
  outerRadius = 78,
  centerLabel,
  centerValue,
}: {
  data: { name: string; value: number; color: string }[]
  height?: number
  innerRadius?: number
  outerRadius?: number
  centerLabel?: string
  centerValue?: string
}) {
  const total = data.reduce((sum, item) => sum + item.value, 0)
  return (
    <div className="relative">
      <ResponsiveContainer width="100%" height={height}>
        <PieChart>
          <Pie data={data} dataKey="value" nameKey="name" innerRadius={innerRadius} outerRadius={outerRadius} paddingAngle={2} strokeWidth={0}>
            {data.map((item) => (
              <Cell key={item.name} fill={item.color} />
            ))}
          </Pie>
          <Tooltip contentStyle={tooltipStyle} formatter={(value: number, name: string) => [`${value} (${total ? Math.round((value / total) * 100) : 0}%)`, name]} />
        </PieChart>
      </ResponsiveContainer>
      {(centerLabel || centerValue) && (
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-xl font-semibold text-slate-900 dark:text-slate-50">{centerValue}</span>
          <span className="text-[10px] uppercase tracking-wide text-slate-500">{centerLabel}</span>
        </div>
      )}
    </div>
  )
}
