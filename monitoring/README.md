# Monitoring integration

CloudOps Sentinel exposes Prometheus metrics at `GET /metrics` (no authentication, intended for internal
scraping only — do not expose it publicly).

## Exposed series

| Metric | Type | Meaning |
| --- | --- | --- |
| `sentinel_instances_total` | gauge | Inventory rows |
| `sentinel_instances_running` | gauge | Rows with `status=running` |
| `sentinel_incidents_critical_open` | gauge | Open critical incidents |
| `sentinel_findings_open` | gauge | Open security findings |
| `sentinel_metric_samples` | gauge | Stored telemetry samples |

## Use it

```bash
# quick check
curl -s localhost:8000/metrics

# Prometheus
prometheus --config.file=monitoring/prometheus.yml
```

Then query in Prometheus (`sentinel_incidents_critical_open`) or point Grafana at it as a data source.

`alert-rules.yml` contains four example rules: zero running instances, open critical incidents, a security
finding backlog, and stalled telemetry.

## What is not included

No Grafana dashboard JSON is shipped, because a dashboard that was never loaded and verified would be a
decorative artifact. Build one from the five series above — it takes a few minutes — or query Prometheus
directly.

## Related in-app monitoring

The platform's own monitoring engine (thresholds, alerts, incidents) is independent of Prometheus. See
`docs/architecture.md` §3 for the collection pipeline.
