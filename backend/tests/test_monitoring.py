from __future__ import annotations


def test_inventory_lists_seeded_fleet(client, admin_headers):
    response = client.get("/api/v1/instances", headers=admin_headers)
    assert response.status_code == 200
    items = response.json()
    assert len(items) >= 8
    sources = {item["source"] for item in items}
    assert "local" in sources
    assert "simulated" in sources


def test_instance_detail_contains_metrics_and_provenance(client, admin_headers):
    items = client.get("/api/v1/instances", headers=admin_headers).json()
    target = next(item for item in items if item["source"] == "simulated")
    response = client.get(f"/api/v1/instances/{target['id']}", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["latest_metric"] is not None
    assert body["statistics"]["samples"] > 0
    assert "simulator" in body["data_note"].lower() or "synthetic" in body["data_note"].lower()


def test_metric_history_is_time_ordered(client, admin_headers):
    items = client.get("/api/v1/instances", headers=admin_headers).json()
    target = next(item for item in items if item["source"] == "simulated")
    response = client.get(
        f"/api/v1/instances/{target['id']}/metrics?hours=6", headers=admin_headers
    )
    assert response.status_code == 200
    points = response.json()
    assert len(points) > 10
    timestamps = [point["timestamp"] for point in points]
    assert timestamps == sorted(timestamps)


def test_manual_collection_cycle(client, engineer_headers):
    response = client.post("/api/v1/monitoring/collect", headers=engineer_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["simulated_samples"] >= 7
    assert isinstance(body["errors"], list)


def test_spike_generates_critical_alert(client, engineer_headers, admin_headers):
    items = client.get("/api/v1/instances", headers=admin_headers).json()
    target = next(item for item in items if item["source"] == "simulated" and item["status"] == "running")

    spike = client.post(
        "/api/v1/monitoring/spike",
        json={"instance_id": target["id"], "metric": "cpu_percent", "value": 99.5, "minutes": 2},
        headers=engineer_headers,
    )
    assert spike.status_code == 200, spike.text

    client.post("/api/v1/monitoring/collect", headers=engineer_headers)
    alerts = client.get("/api/v1/monitoring/alerts", headers=admin_headers).json()
    matching = [alert for alert in alerts if alert["instance_id"] == target["id"]]
    assert matching, alerts
    assert matching[0]["level"] == "critical"
    assert matching[0]["value"] >= 90


def test_threshold_validation(client, admin_headers):
    bad = client.patch(
        "/api/v1/monitoring/thresholds/cpu_percent",
        json={"warning": 95, "critical": 80},
        headers=admin_headers,
    )
    assert bad.status_code == 422

    good = client.patch(
        "/api/v1/monitoring/thresholds/cpu_percent",
        json={"warning": 68, "critical": 91},
        headers=admin_headers,
    )
    assert good.status_code == 200
    assert good.json()["warning"] == 68


def test_monitoring_summary_shape(client, admin_headers):
    response = client.get("/api/v1/monitoring/summary", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert "instances" in body
    assert body["metric_samples"] > 0
