export type Severity = 'critical' | 'high' | 'medium' | 'low' | 'info'
export type Health = 'healthy' | 'warning' | 'critical' | 'offline' | 'unknown'
export type DataSource = 'local' | 'simulated' | 'aws'

export interface User {
  id: number
  email: string
  full_name: string
  role: 'admin' | 'engineer' | 'analyst' | 'viewer'
  is_active: boolean
  must_change_password: boolean
  last_login_at: string | null
  created_at: string | null
}

export interface TokenResponse {
  access_token: string
  token_type: string
  expires_in: number
  user: User
}

export interface Instance {
  id: number
  name: string
  external_id: string | null
  provider: string
  source: DataSource
  instance_type: string
  region: string
  environment: string
  status: string
  hostname: string | null
  os_name: string | null
  private_ip: string | null
  public_ip: string | null
  cpu_cores: number
  memory_mb: number
  disk_gb: number
  monthly_cost_usd: number
  tags: Record<string, unknown>
  health_status: Health
  last_seen_at: string | null
}

export interface Metric {
  id: number
  instance_id: number
  timestamp: string
  cpu_percent: number
  memory_percent: number
  disk_percent: number
  network_in_kbps: number
  network_out_kbps: number
  load_avg_1m: number
  uptime_seconds: number
  process_count: number
  source: string
}

export interface Alert {
  instance_id: number
  instance_name: string
  metric: string
  value: number
  threshold: number
  level: 'warning' | 'critical'
  message: string
  timestamp: string
  source: string
}

export interface Threshold {
  id: number
  metric: string
  display_name: string
  unit: string
  warning: number
  critical: number
  enabled: boolean
}

export interface Finding {
  id: number
  finding_key: string
  title: string
  severity: Severity
  category: string
  resource_name: string
  resource_type: string
  description: string
  evidence: string
  remediation: string
  scan_source: string
  source_kind: 'simulated' | 'aws' | 'tool' | 'rule-engine'
  scan_id: string | null
  status: 'open' | 'acknowledged' | 'resolved' | 'false_positive'
  first_seen_at: string
  last_seen_at: string
}

export interface ScanToolResult {
  tool: string
  status: 'executed' | 'skipped' | 'failed'
  reason: string | null
  findings: number
  duration_ms: number
}

export interface ScanResult {
  scan_id: string
  started_at: string
  finished_at: string
  findings_created: number
  findings_updated: number
  findings_resolved: number
  tools: ScanToolResult[]
  simulated_resources: boolean
  aws_connected: boolean
}

export interface SecuritySummary {
  counts: Record<string, number>
  total: number
  risk_score: number
  risk_level: string
  categories: { category: string; count: number }[]
  last_scan_at: string | null
  findings_total: number
}

export interface CostSummary {
  period: string
  estimated_monthly_usd: number
  month_to_date_usd: number
  forecast_usd: number
  previous_month_usd: number
  change_percent: number
  budget_usd: number
  budget_used_percent: number
  potential_savings_usd: number
  currency: string
  source: string
  breakdown: { instance_id: number; name: string; type: string; environment: string; source: string; monthly_usd: number }[]
  instance_count: number
  idle_instance_count: number
}

export interface CostRecommendation {
  id: string
  instance_id: number | null
  instance_name: string
  type: 'idle' | 'oversized' | 'unattached_storage' | 'commitment' | 'scheduling'
  title: string
  description: string
  current_monthly_usd: number
  projected_monthly_usd: number
  monthly_savings_usd: number
  confidence: 'low' | 'medium' | 'high'
  evidence: Record<string, unknown>
  action: string
}

export interface PricingRow {
  id: number
  instance_type: string
  vcpu: number
  memory_gb: number
  hourly_usd: number
  ebs_gb_usd: number
  description: string | null
}

export interface LogEntry {
  id: number
  service: string
  level: string
  severity: 'critical' | 'error' | 'warning' | 'info'
  message: string
  timestamp: string
  fingerprint: string
  trace_id: string | null
  instance_id: number | null
  log_metadata: Record<string, unknown>
}

export interface LogGroup {
  fingerprint: string
  service: string
  severity: string
  sample_message: string
  count: number
  first_seen: string
  last_seen: string
  affected_traces: number
}

export interface LogAnalysis {
  source: 'ai' | 'rule-based'
  summary: string
  likely_causes: string[]
  hypotheses: { id: string; summary: string; confidence: string; evidence: string; causes: string[] }[]
  debug_commands: string[]
  next_steps: string[]
  confidence: 'low' | 'medium' | 'high'
  disclaimer: string
  related_incidents: { id: number; incident_number: string; title: string; severity: string; status: string }[]
  log_count?: number
  services?: string[]
}

export interface IncidentNote {
  id: number
  incident_id: number
  author: string
  note: string
  note_type: string
  status_change: string | null
  created_at: string
}

export interface Incident {
  id: number
  incident_number: string
  title: string
  description: string
  severity: Severity
  status: 'detected' | 'acknowledged' | 'investigating' | 'resolved' | 'closed'
  service: string | null
  instance_id: number | null
  assigned_to: string | null
  detected_by: string
  acknowledged_at: string | null
  resolved_at: string | null
  closed_at: string | null
  resolution_summary: string | null
  created_at: string
  updated_at: string
}

export interface IncidentDetail extends Incident {
  notes: IncidentNote[]
  duration_minutes: number | null
}

export interface IncidentStats {
  total: number
  open: number
  by_status: Record<string, number>
  by_severity: Record<string, number>
  critical_open: number
  mttr_minutes: number | null
  mtta_minutes: number | null
  last_7_days: number
  risk_score: number
}

export interface ActionSpec {
  name: string
  label: string
  description: string
  risk: 'low' | 'medium' | 'high'
  destructive: boolean
  requires_approval: boolean
  supports_dry_run: boolean
  categories: string[]
}

export interface RemediationAction {
  id: number
  rule_id: number | null
  incident_id: number | null
  instance_id: number | null
  action_name: string
  target: string
  status: 'pending_approval' | 'approved' | 'rejected' | 'running' | 'succeeded' | 'failed' | 'dry_run'
  dry_run: boolean
  requested_by: string
  approved_by: string | null
  rejection_reason: string | null
  output: string | null
  error: string | null
  health_check_before: string | null
  health_check_after: string | null
  created_at: string
  approved_at: string | null
  executed_at: string | null
}

export interface RemediationRule {
  id: number
  name: string
  description: string
  metric: string
  operator: string
  threshold: number
  duration_minutes: number
  action_name: string
  target_scope: string
  enabled: boolean
  requires_approval: boolean
  dry_run: boolean
}

export interface Deployment {
  id: number
  service: string
  environment: string
  version: string
  commit_sha: string | null
  status: string
  pipeline: string
  stage: string
  triggered_by: string
  source: string
  duration_seconds: number
  started_at: string
  finished_at: string | null
  detail: Record<string, unknown>
}

export interface Pipeline {
  name: string
  platform: string
  config_path: string
  detected: boolean
  last_run: Deployment | null
  success_rate: number
  total_runs: number
  stages: string[]
}

export interface AwsStatus {
  mode: 'simulated' | 'connected' | 'not_configured' | 'error'
  connected: boolean
  region: string
  account_id: string | null
  identity: string | null
  message: string
  checked_at: string
  simulation_mode: boolean
}

export interface AwsResource {
  resource_id: string
  name: string
  type: string
  region: string
  state: string | null
  detail: Record<string, any>
  source: 'aws' | 'simulated'
}

export interface AuditEntry {
  id: number
  actor: string
  action: string
  entity_type: string
  entity_id: string | null
  detail: Record<string, unknown>
  ip_address: string | null
  created_at: string
}

export interface NotificationItem {
  id: number
  title: string
  message: string
  severity: string
  category: string
  is_read: boolean
  entity_type: string | null
  entity_id: string | null
  created_at: string
}

export interface Overview {
  generated_at: string
  mode: { aws: string; data_sources: Record<string, number>; scheduler: boolean }
  instances: { total: number; by_health: Record<string, number>; by_source: Record<string, number>; running: number }
  utilisation: { cpu: number | null; memory: number | null; disk: number | null }
  incidents: { open: number; critical: number; high: number; total: number }
  security: { open_findings: number; critical: number; high: number; risk_score: number; risk_level: string }
  cost: { estimated_monthly_usd: number; budget_usd: number; budget_used_percent: number; potential_savings_usd: number; currency: string; source: string }
  deployments: { last_status: string; last_service: string | null; last_version: string | null; last_at: string | null; success_rate: number; source: string | null }
  logs: { errors_24h: number }
  remediation: { pending_approvals: number }
  notifications: { unread: number }
  alerts: Alert[]
  trend: { bucket: string; cpu: number; memory: number; disk: number }[]
  recent_incidents: Incident[]
  recent_findings: Finding[]
}

export interface Paginated<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  pages: number
}

export interface RuntimeInfo {
  product: string
  version: string
  environment: string
  database: string
  database_url_masked: string
  scheduler_enabled: boolean
  monitoring_interval_seconds: number
  local_collector: boolean
  aws_mode: string
  aws_region: string
  ai_provider: string
  ai_enabled: boolean
  log_retention_days: number
  cors_origins: string[]
  warnings: string[]
  database_size_bytes: number | null
  tools: Record<string, boolean>
}

export interface InstanceDetailResponse {
  instance: Instance
  latest_metric: Metric | null
  alerts: { metric: string; display_name: string; value: number; unit: string; level: string; threshold: number }[]
  statistics: { avg_cpu: number; avg_memory: number; peak_cpu: number; samples: number }
  estimated_monthly_usd: number
  data_note: string
}
