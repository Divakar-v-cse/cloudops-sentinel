from __future__ import annotations


def test_dashboard_overview_aggregates_all_modules(client, admin_headers):
    response = client.get("/api/v1/dashboard/overview", headers=admin_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    for key in ("instances", "utilisation", "incidents", "security", "cost", "deployments", "alerts", "trend"):
        assert key in body
    assert body["instances"]["total"] >= 8
    assert body["cost"]["source"] == "estimated"
    assert body["mode"]["data_sources"]["simulated"] >= 7


def test_aws_status_is_honest_about_simulation(client, admin_headers):
    response = client.get("/api/v1/aws/status", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "simulated"
    assert body["connected"] is False
    assert "simulation" in body["message"].lower()


def test_aws_inventory_is_labelled(client, admin_headers):
    for path in ("ec2", "s3", "iam", "security-groups"):
        response = client.get(f"/api/v1/aws/{path}", headers=admin_headers)
        assert response.status_code == 200, path
        body = response.json()
        assert body["source"] == "simulated"
        assert all(item["source"] == "simulated" for item in body["items"])


def test_cloudwatch_refuses_to_invent_metrics(client, admin_headers):
    response = client.get(
        "/api/v1/aws/cloudwatch?instance_id=i-0a1f2b3c4d5e6f701", headers=admin_headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "simulated"
    assert body["datapoints"] == []
    assert "connected mode" in body["message"]


def test_pipelines_detected_from_repository(client, admin_headers):
    pipelines = client.get("/api/v1/pipelines", headers=admin_headers).json()
    assert len(pipelines) == 4
    names = {item["name"] for item in pipelines}
    assert "sentinel-ci" in names
    ci = next(item for item in pipelines if item["name"] == "sentinel-ci")
    assert ci["platform"] == "github-actions"
    assert ci["total_runs"] >= 1


def test_deployment_ingest_marks_source_as_pipeline(client, engineer_headers):
    response = client.post(
        "/api/v1/deployments",
        json={
            "service": "cart-service",
            "environment": "staging",
            "version": "v0.0.1-test",
            "status": "success",
            "duration_seconds": 42,
            "pipeline": "sentinel-ci",
        },
        headers=engineer_headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["source"] == "pipeline"

    failed = client.post(
        "/api/v1/deployments",
        json={"service": "cart-service", "version": "v0.0.2-test", "status": "failed"},
        headers=engineer_headers,
    )
    assert failed.status_code == 201


def test_audit_log_records_privileged_actions(client, admin_headers):
    response = client.get("/api/v1/audit?page_size=100", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    actions = {item["action"] for item in body["items"]}
    assert "auth.login" in actions
    assert any(action.startswith("security.scan") for action in actions)

    facets = client.get("/api/v1/audit/facets", headers=admin_headers).json()
    assert facets["total"] > 0


def test_notifications_can_be_read(client, admin_headers):
    items = client.get("/api/v1/notifications", headers=admin_headers).json()
    assert items
    target = items[0]
    marked = client.post(f"/api/v1/notifications/{target['id']}/read", headers=admin_headers)
    assert marked.status_code == 200
    assert marked.json()["is_read"] is True


def test_runtime_settings_hide_secrets(client, admin_headers):
    response = client.get("/api/v1/settings/runtime", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["product"] == "CloudOps Sentinel"
    assert "***" in body["database_url_masked"] or "sqlite" in body["database_url_masked"]
    assert "secret" not in str(body).lower() or "***" in str(body).lower()


def test_local_instance_cannot_be_powered_off(client, admin_headers):
    instances = client.get("/api/v1/instances", headers=admin_headers).json()
    local = next(item for item in instances if item["source"] == "local")
    response = client.post(f"/api/v1/instances/{local['id']}/power?action=stop", headers=admin_headers)
    assert response.status_code == 403
