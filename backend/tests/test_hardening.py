"""Regression tests for input-validation and routing defects.

Each test corresponds to a real bug found while exercising the API with
malformed payloads: unvalidated dict bodies that produced 500s, a query
parameter that rejected numeric ids, and a status value the state machine
did not understand.
"""
from __future__ import annotations


def _first_instance(client, headers):
    rows = client.get("/api/v1/instances", headers=headers).json()
    return next(row for row in rows if row["source"] == "simulated")


def test_unknown_field_is_rejected_instead_of_silently_ignored(client, admin_headers):
    response = client.patch(
        "/api/v1/monitoring/thresholds/cpu_percent",
        json={"warning_percent": 60},  # typo: the field is "warning"
        headers=admin_headers,
    )
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["detail"], "validation detail should be present"
    assert "warning_percent" in response.text


def test_threshold_bounds_still_validated(client, admin_headers):
    response = client.patch(
        "/api/v1/monitoring/thresholds/cpu_percent",
        json={"warning": 95, "critical": 80},
        headers=admin_headers,
    )
    assert response.status_code == 422
    assert "greater than warning" in response.text


def test_spike_rejects_non_numeric_minutes(client, admin_headers):
    instance = _first_instance(client, admin_headers)
    response = client.post(
        "/api/v1/monitoring/spike",
        json={"instance_id": instance["id"], "metric": "cpu_percent", "value": 90, "minutes": "soon"},
        headers=admin_headers,
    )
    assert response.status_code == 422, response.text


def test_spike_rejects_out_of_range_value(client, admin_headers):
    instance = _first_instance(client, admin_headers)
    response = client.post(
        "/api/v1/monitoring/spike",
        json={"instance_id": instance["id"], "metric": "cpu_percent", "value": 400},
        headers=admin_headers,
    )
    assert response.status_code == 422


def test_log_analysis_rejects_bad_hours(client, admin_headers):
    response = client.post("/api/v1/logs/analyze", json={"hours": "yesterday"}, headers=admin_headers)
    assert response.status_code == 422, response.text

    zero = client.post("/api/v1/logs/analyze", json={"hours": 0}, headers=admin_headers)
    assert zero.status_code == 422


def test_log_analysis_accepts_valid_window(client, admin_headers):
    response = client.post("/api/v1/logs/analyze", json={"hours": 24}, headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["source"] in {"ai", "rule-based"}
    assert "not a confirmed root cause" in body["disclaimer"].lower()


def test_pricing_rejects_non_numeric_value(client, admin_headers):
    response = client.patch(
        "/api/v1/costs/pricing/t3.small", json={"hourly_usd": "cheap"}, headers=admin_headers
    )
    assert response.status_code == 422, response.text


def test_pricing_requires_at_least_one_field(client, admin_headers):
    response = client.patch("/api/v1/costs/pricing/t3.small", json={}, headers=admin_headers)
    assert response.status_code == 422


def test_finding_status_is_typed(client, admin_headers):
    findings = client.get("/api/v1/security/findings?status=all&page_size=1", headers=admin_headers).json()
    finding_id = findings["items"][0]["id"]
    bad = client.patch(
        f"/api/v1/security/findings/{finding_id}", json={"status": "ignored"}, headers=admin_headers
    )
    assert bad.status_code == 422
    good = client.patch(
        f"/api/v1/security/findings/{finding_id}", json={"status": "acknowledged"}, headers=admin_headers
    )
    assert good.status_code == 200
    assert good.json()["status"] == "acknowledged"


def test_cloudwatch_accepts_numeric_instance_id(client, admin_headers):
    instance = _first_instance(client, admin_headers)
    response = client.get(
        f"/api/v1/aws/cloudwatch?instance_id={instance['id']}", headers=admin_headers
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source"] in {"simulated", "aws"}
    assert "datapoints" in body


def test_cloudwatch_unknown_instance_is_404(client, admin_headers):
    response = client.get("/api/v1/aws/cloudwatch?instance_id=999999", headers=admin_headers)
    assert response.status_code == 404


def test_incident_reopen_maps_to_detected(client, engineer_headers):
    created = client.post(
        "/api/v1/incidents",
        json={"title": "Reopen flow check", "severity": "low", "service": "checkout-api"},
        headers=engineer_headers,
    )
    assert created.status_code == 201
    incident_id = created.json()["id"]

    for target, extra in (
        ("acknowledged", {}),
        ("investigating", {}),
        ("resolved", {"resolution_summary": "fixed by rollback", "resolution_category": "deployment"}),
        ("closed", {}),
    ):
        response = client.post(
            f"/api/v1/incidents/{incident_id}/status",
            json={"status": target, **extra},
            headers=engineer_headers,
        )
        assert response.status_code == 200, f"{target}: {response.text}"

    reopened = client.post(
        f"/api/v1/incidents/{incident_id}/status", json={"status": "reopened"}, headers=engineer_headers
    )
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["status"] == "detected"


def test_versioned_health_alias(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] in {"ok", "degraded"}


def test_incident_update_rejects_unknown_severity(client, engineer_headers):
    created = client.post(
        "/api/v1/incidents",
        json={"title": "Severity validation check", "severity": "low"},
        headers=engineer_headers,
    )
    incident_id = created.json()["id"]
    response = client.patch(
        f"/api/v1/incidents/{incident_id}", json={"severity": "apocalyptic"}, headers=engineer_headers
    )
    assert response.status_code == 422
