export function parseUtc(value: string | null | undefined): Date | null {
  if (!value) return null
  const normalised = /[zZ]|[+-]\d{2}:\d{2}$/.test(value) ? value : `${value}Z`
  const date = new Date(normalised)
  return Number.isNaN(date.getTime()) ? null : date
}

export function formatDateTime(value: string | null | undefined): string {
  const date = parseUtc(value)
  if (!date) return '—'
  return date.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function formatTime(value: string | null | undefined): string {
  const date = parseUtc(value)
  if (!date) return '—'
  return date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
}

export function timeAgo(value: string | null | undefined): string {
  const date = parseUtc(value)
  if (!date) return '—'
  const seconds = Math.floor((Date.now() - date.getTime()) / 1000)
  if (seconds < 45) return 'just now'
  if (seconds < 90) return '1 min ago'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} h ago`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days} d ago`
  return formatDateTime(value)
}

export function formatMoney(value: number | null | undefined, currency = 'USD'): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return new Intl.NumberFormat(undefined, {
    style: 'currency',
    currency,
    maximumFractionDigits: value >= 100 ? 0 : 2,
  }).format(value)
}

export function formatNumber(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return value.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: 0 })
}

export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return '—'
  return `${formatNumber(value, digits)}%`
}

export function formatBytes(value: number | null | undefined): string {
  if (!value) return '—'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let size = value
  let index = 0
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024
    index += 1
  }
  return `${size.toFixed(size >= 10 ? 0 : 1)} ${units[index]}`
}

export function formatDuration(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined) return '—'
  if (minutes < 60) return `${Math.round(minutes)} min`
  const hours = Math.floor(minutes / 60)
  const rest = Math.round(minutes % 60)
  return rest ? `${hours}h ${rest}m` : `${hours}h`
}

export function truncate(value: string, length = 90): string {
  return value.length > length ? `${value.slice(0, length)}…` : value
}

export const severityRank: Record<string, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
  info: 4,
  warning: 2,
  healthy: 4,
  error: 1,
}

export function severityBadge(severity: string): string {
  const key = severity?.toLowerCase()
  if (key === 'critical') return 'badge badge-critical'
  if (key === 'high' || key === 'error') return 'badge badge-high'
  if (key === 'medium' || key === 'warning') return 'badge badge-medium'
  if (key === 'low') return 'badge badge-low'
  if (key === 'healthy' || key === 'success' || key === 'succeeded' || key === 'running') return 'badge badge-success'
  if (key === 'info') return 'badge badge-info'
  return 'badge badge-neutral'
}

export function healthBadge(health: string): string {
  switch (health) {
    case 'healthy':
    case 'running':
      return 'badge badge-success'
    case 'warning':
      return 'badge badge-medium'
    case 'critical':
      return 'badge badge-critical'
    case 'offline':
    case 'stopped':
      return 'badge badge-neutral'
    case 'unknown':
      return 'badge badge-neutral'
    default:
      return 'badge badge-info'
  }
}

export const chartColors = {
  cpu: '#3186fb',
  memory: '#8b5cf6',
  disk: '#f59e0b',
  network: '#10b981',
  grid: 'rgba(100, 116, 139, 0.18)',
  text: 'rgba(100, 116, 139, 0.9)',
}
