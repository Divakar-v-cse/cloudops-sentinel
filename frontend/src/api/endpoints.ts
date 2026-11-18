import { api } from './client'
import type {
  Alert,
  AuditEntry,
  AwsResource,
  AwsStatus,
  CostRecommendation,
  CostSummary,
  Deployment,
  Finding,
  Incident,
  IncidentDetail,
  IncidentNote,
  IncidentStats,
  Instance,
  InstanceDetailResponse,
  LogAnalysis,
  LogEntry,
  LogGroup,
  Metric,
  NotificationItem,
  Overview,
  Paginated,
  Pipeline,
  PricingRow,
  RemediationAction,
  RemediationRule,
  RuntimeInfo,
  ScanResult,
  SecuritySummary,
  ActionSpec,
  Threshold,
  TokenResponse,
  User,
} from '../types'

const unwrap = <T>(promise: Promise<{ data: T }>) => promise.then((response) => response.data)

export const authApi = {
  login: (email: string, password: string) =>
    unwrap<TokenResponse>(api.post('/auth/login', { email, password })),
  me: () => unwrap<User>(api.get('/auth/me')),
  changePassword: (current_password: string, new_password: string) =>
    unwrap<User>(api.post('/auth/change-password', { current_password, new_password })),
  users: () => unwrap<User[]>(api.get('/auth/users')),
  createUser: (payload: { email: string; full_name: string; password: string; role: string }) =>
    unwrap<User>(api.post('/auth/users', payload)),
  setUserActive: (id: number, active: boolean) =>
    unwrap<User>(api.patch(`/auth/users/${id}/status?active=${active}`)),
}

export const dashboardApi = {
  overview: () => unwrap<Overview>(api.get('/dashboard/overview')),
  trend: (hours = 12) => unwrap<{ bucket: string; cpu: number; memory: number; disk: number }[]>(
    api.get('/dashboard/trend', { params: { hours } }),
  ),
}

export const instancesApi = {
  list: (params?: Record<string, unknown>) => unwrap<Instance[]>(api.get('/instances', { params })),
  get: (id: number) => unwrap<InstanceDetailResponse>(api.get(`/instances/${id}`)),
  metrics: (id: number, hours = 6) => unwrap<Metric[]>(api.get(`/instances/${id}/metrics`, { params: { hours } })),
  create: (payload: Record<string, unknown>) => unwrap<Instance>(api.post('/instances', payload)),
  update: (id: number, payload: Record<string, unknown>) => unwrap<Instance>(api.patch(`/instances/${id}`, payload)),
  power: (id: number, action: 'start' | 'stop' | 'reboot') =>
    unwrap<{ status: string; simulated: boolean }>(api.post(`/instances/${id}/power?action=${action}`)),
  remove: (id: number) => unwrap<{ deleted: number }>(api.delete(`/instances/${id}`)),
}

export const monitoringApi = {
  summary: () => unwrap<{
    instances: { total: number; by_health: Record<string, number>; by_source: Record<string, number>; running: number }
    utilisation: { cpu: number | null; memory: number | null; disk: number | null }
    thresholds: Threshold[]
    interval_seconds: number
    retention_hours: number
    scheduler_running: boolean
    local_collector: boolean
    metric_samples: number
    data_sources: string[]
  }>(api.get('/monitoring/summary')),
  alerts: (limit = 20) => unwrap<Alert[]>(api.get('/monitoring/alerts', { params: { limit } })),
  thresholds: () => unwrap<Threshold[]>(api.get('/monitoring/thresholds')),
  updateThreshold: (metric: string, payload: { warning?: number; critical?: number; enabled?: boolean }) =>
    unwrap<Threshold>(api.patch(`/monitoring/thresholds/${metric}`, payload)),
  collect: () => unwrap<{ local_samples: number; simulated_samples: number; errors: string[] }>(
    api.post('/monitoring/collect'),
  ),
  spike: (payload: { instance_id: number; metric: string; value: number; minutes: number }) =>
    unwrap<{ message: string }>(api.post('/monitoring/spike', payload)),
  fleet: () => unwrap<{ instance: Instance; cpu_percent: number | null; memory_percent: number | null; disk_percent: number | null; timestamp: string | null }[]>(
    api.get('/monitoring/fleet'),
  ),
  metrics: (params: { instance_id?: number; hours?: number }) => unwrap<Metric[]>(api.get('/monitoring/metrics', { params })),
}

export const securityApi = {
  findings: (params: Record<string, unknown>) => unwrap<Paginated<Finding>>(api.get('/security/findings', { params })),
  summary: () => unwrap<SecuritySummary>(api.get('/security/summary')),
  scan: (payload: { tools: string[]; include_cloud: boolean }) => unwrap<ScanResult>(api.post('/security/scan', payload)),
  tools: () => unwrap<{ tools: { name: string; kind: string; available: boolean; purpose: string }[]; note: string }>(
    api.get('/security/tools'),
  ),
  setStatus: (id: number, status: string) => unwrap<Finding>(api.patch(`/security/findings/${id}`, { status })),
  reportUrl: (format: 'json' | 'csv') => `/security/report?format=${format}&status=open`,
}

export const costApi = {
  summary: () => unwrap<CostSummary>(api.get('/costs/summary')),
  trend: () => unwrap<{ period: string; estimated_usd: number; actual_usd: number | null }[]>(api.get('/costs/trend')),
  recommendations: () => unwrap<CostRecommendation[]>(api.get('/costs/recommendations')),
  pricing: () => unwrap<PricingRow[]>(api.get('/costs/pricing')),
  updatePricing: (type: string, payload: { hourly_usd?: number; ebs_gb_usd?: number }) =>
    unwrap<PricingRow>(api.patch(`/costs/pricing/${encodeURIComponent(type)}`, payload)),
  setBudget: (budget_usd: number) => unwrap<{ budget_usd: number }>(api.put('/costs/budget', { budget_usd })),
  snapshot: () => unwrap<{ period: string; total_usd: number }>(api.post('/costs/snapshot')),
}

export const logsApi = {
  search: (params: Record<string, unknown>) => unwrap<Paginated<LogEntry>>(api.get('/logs', { params })),
  groups: (params: { hours?: number; service?: string }) => unwrap<LogGroup[]>(api.get('/logs/groups', { params })),
  stats: (hours = 24) => unwrap<{
    window_hours: number
    total: number
    by_severity: Record<string, number>
    top_services: { service: string; count: number }[]
    timeline: { bucket: string; severity: string; count: number }[]
  }>(api.get('/logs/stats', { params: { hours } })),
  services: () => unwrap<{ service: string; count: number }[]>(api.get('/logs/services')),
  analyze: (payload: { fingerprint?: string; service?: string; hours?: number; log_ids?: number[] }) =>
    unwrap<LogAnalysis>(api.post('/logs/analyze', payload)),
  ingest: (logs: Record<string, unknown>[]) => unwrap<{ ingested: number }>(api.post('/logs', { logs })),
  cleanup: (days?: number) => unwrap<{ deleted: number }>(api.post('/logs/retention/cleanup', null, { params: { days } })),
}

export const incidentsApi = {
  list: (params: Record<string, unknown>) => unwrap<Paginated<Incident>>(api.get('/incidents', { params })),
  get: (id: number) => unwrap<IncidentDetail>(api.get(`/incidents/${id}`)),
  stats: () => unwrap<IncidentStats>(api.get('/incidents/stats')),
  create: (payload: Record<string, unknown>) => unwrap<IncidentDetail>(api.post('/incidents', payload)),
  update: (id: number, payload: Record<string, unknown>) => unwrap<IncidentDetail>(api.patch(`/incidents/${id}`, payload)),
  changeStatus: (id: number, payload: Record<string, unknown>) =>
    unwrap<IncidentDetail>(api.post(`/incidents/${id}/status`, payload)),
  addNote: (id: number, note: string, note_type = 'investigation') =>
    unwrap<IncidentNote>(api.post(`/incidents/${id}/notes`, { note, note_type })),
}

export const remediationApi = {
  catalog: () => unwrap<ActionSpec[]>(api.get('/remediation/catalog')),
  rules: () => unwrap<RemediationRule[]>(api.get('/remediation/rules')),
  createRule: (payload: Record<string, unknown>) => unwrap<RemediationRule>(api.post('/remediation/rules', payload)),
  updateRule: (id: number, payload: Record<string, unknown>) => unwrap<RemediationRule>(api.patch(`/remediation/rules/${id}`, payload)),
  deleteRule: (id: number) => unwrap<{ deleted: number }>(api.delete(`/remediation/rules/${id}`)),
  actions: (params?: Record<string, unknown>) => unwrap<Paginated<RemediationAction>>(api.get('/remediation/actions', { params })),
  request: (payload: Record<string, unknown>) => unwrap<RemediationAction>(api.post('/remediation/actions', payload)),
  approve: (id: number, note?: string) => unwrap<RemediationAction>(api.post(`/remediation/actions/${id}/approve`, { note })),
  reject: (id: number, note?: string) => unwrap<RemediationAction>(api.post(`/remediation/actions/${id}/reject`, { note })),
  execute: (id: number) => unwrap<RemediationAction>(api.post(`/remediation/actions/${id}/execute`)),
  evaluate: () => unwrap<{ actions_created: number }>(api.post('/remediation/evaluate')),
}

export const deploymentsApi = {
  list: (params?: Record<string, unknown>) => unwrap<Paginated<Deployment>>(api.get('/deployments', { params })),
  summary: () => unwrap<{
    total_deployments: number
    successful: number
    failed: number
    success_rate: number
    last_deployment: Record<string, unknown> | null
    deployments_last_7_days: number
  }>(api.get('/deployments/summary')),
  pipelines: () => unwrap<Pipeline[]>(api.get('/pipelines')),
}

export const awsApi = {
  status: () => unwrap<AwsStatus>(api.get('/aws/status')),
  ec2: () => unwrap<{ items: AwsResource[]; count: number; source: string }>(api.get('/aws/ec2')),
  s3: () => unwrap<{ items: AwsResource[]; count: number; source: string }>(api.get('/aws/s3')),
  iam: () => unwrap<{ items: AwsResource[]; count: number; source: string }>(api.get('/aws/iam')),
  securityGroups: () => unwrap<{ items: AwsResource[]; count: number; source: string }>(api.get('/aws/security-groups')),
  guide: () => unwrap<{ current_mode: string; steps: string[]; permissions_used: string[]; safety: string[] }>(api.get('/aws/guide')),
  refresh: () => unwrap<AwsStatus>(api.post('/aws/refresh')),
}

export const platformApi = {
  audit: (params: Record<string, unknown>) => unwrap<Paginated<AuditEntry>>(api.get('/audit', { params })),
  auditFacets: () => unwrap<{ actions: { action: string; count: number }[]; entity_types: { entity_type: string; count: number }[]; total: number }>(
    api.get('/audit/facets'),
  ),
  notifications: (limit = 30) => unwrap<NotificationItem[]>(api.get('/notifications', { params: { limit } })),
  markRead: (id: number) => unwrap<NotificationItem>(api.post(`/notifications/${id}/read`)),
  markAllRead: () => unwrap<{ updated: number }>(api.post('/notifications/read-all')),
  runtime: () => unwrap<RuntimeInfo>(api.get('/settings/runtime')),
  settings: () => unwrap<{ settings: { key: string; value: unknown; description: string | null; updated_at: string }[]; runtime: RuntimeInfo }>(api.get('/settings')),
  updateRetention: (days: number) => unwrap<{ retention_days: number }>(api.patch('/settings/log-retention', null, { params: { days } })),
  cleanup: () => unwrap<{ deleted: number; retention_days: number }>(api.post('/settings/cleanup')),
  health: () => unwrap<{ status: string; version: string; database: string }>(api.get('/../health')),
}
