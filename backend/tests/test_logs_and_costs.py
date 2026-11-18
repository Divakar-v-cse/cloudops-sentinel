from __future__ import annotations


def test_log_ingest_classifies_severity(client, engineer_headers):
    payload = {
        "logs": [
            {"service": "checkout-api", "level": "ERROR", "message": "Payment provider timeout after 3000ms"},
            {"service": "order-worker", "level": "WARN", "message": "Container terminated with reason OOMKilled"},
            {"service": "web-frontend", "level": "INFO", "message": "GET /health 200"},
        ]
    }
    response = client.post("/api/v1/logs", json=payload, headers=engineer_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ingested"] == 3
    assert body["severity_counts"]["error"] == 1
    # OOMKilled is escalated even though the level was WARN
    assert body["severity_counts"]["critical"] == 1


def test_log_search_filters_by_service_and_text(client, admin_headers):
    response = client.get(
        "/api/v1/logs?service=checkout-api&query=timeout&hours=720", headers=admin_headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1
    assert all(item["service"] == "checkout-api" for item in body["items"])


def test_log_grouping_dedupes_similar_messages(client, admin_headers):
    response = client.get("/api/v1/logs/groups?hours=720", headers=admin_headers)
    assert response.status_code == 200
    groups = response.json()
    assert groups
    assert groups[0]["count"] >= 1
    assert len(groups[0]["fingerprint"]) == 16


def test_analysis_uses_rule_based_fallback_without_key(client, admin_headers):
    response = client.post(
        "/api/v1/logs/analyze", json={"service": "order-worker", "hours": 720}, headers=admin_headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "rule-based"
    assert body["summary"]
    assert "not a confirmed root cause" in body["disclaimer"].lower()
    assert body["debug_commands"]


def test_cost_summary_is_labelled_as_estimate(client, admin_headers):
    response = client.get("/api/v1/costs/summary", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "estimated"
    assert body["estimated_monthly_usd"] > 0
    assert body["budget_usd"] > 0
    assert 0 <= body["budget_used_percent"] <= 1000


def test_cost_trend_and_recommendations(client, admin_headers):
    trend = client.get("/api/v1/costs/trend", headers=admin_headers).json()
    assert len(trend) >= 2
    assert all("period" in point for point in trend)

    recs = client.get("/api/v1/costs/recommendations", headers=admin_headers).json()
    assert isinstance(recs, list)
    for rec in recs:
        assert rec["monthly_savings_usd"] >= 0
        assert rec["type"] in {"idle", "oversized", "unattached_storage", "commitment", "scheduling"}


def test_budget_update_requires_admin(client, engineer_headers, admin_headers):
    forbidden = client.put("/api/v1/costs/budget", json={"budget_usd": 5000}, headers=engineer_headers)
    assert forbidden.status_code == 403

    ok = client.put("/api/v1/costs/budget", json={"budget_usd": 4200}, headers=admin_headers)
    assert ok.status_code == 200
    assert ok.json()["budget_usd"] == 4200

    summary = client.get("/api/v1/costs/summary", headers=admin_headers).json()
    assert summary["budget_usd"] == 4200


def test_pricing_update_rejects_negative(client, admin_headers):
    response = client.patch(
        "/api/v1/costs/pricing/t3.medium", json={"hourly_usd": -1}, headers=admin_headers
    )
    assert response.status_code == 422
