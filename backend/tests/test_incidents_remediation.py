from __future__ import annotations


def test_incident_lifecycle_is_enforced(client, engineer_headers):
    created = client.post(
        "/api/v1/incidents",
        json={
            "title": "Elevated 5xx rate on payments-api",
            "description": "Error rate above 2% for 10 minutes.",
            "severity": "high",
            "service": "payments-api",
        },
        headers=engineer_headers,
    )
    assert created.status_code == 201, created.text
    incident = created.json()
    assert incident["incident_number"].startswith("INC-")
    assert incident["status"] == "detected"

    # cannot close before acknowledgement/investigation
    illegal = client.post(
        f"/api/v1/incidents/{incident['id']}/status",
        json={"status": "closed"},
        headers=engineer_headers,
    )
    assert illegal.status_code == 409

    ack = client.post(
        f"/api/v1/incidents/{incident['id']}/status",
        json={"status": "acknowledged", "note": "Looking into it"},
        headers=engineer_headers,
    )
    assert ack.status_code == 200
    assert ack.json()["acknowledged_at"] is not None

    investigate = client.post(
        f"/api/v1/incidents/{incident['id']}/status",
        json={"status": "investigating", "note": "Checking upstream latency"},
        headers=engineer_headers,
    )
    assert investigate.status_code == 200

    # resolution requires a summary
    no_summary = client.post(
        f"/api/v1/incidents/{incident['id']}/status",
        json={"status": "resolved"},
        headers=engineer_headers,
    )
    assert no_summary.status_code == 400

    resolved = client.post(
        f"/api/v1/incidents/{incident['id']}/status",
        json={"status": "resolved", "resolution_summary": "Scaled out API replicas; error rate back to 0.1%."},
        headers=engineer_headers,
    )
    assert resolved.status_code == 200
    assert resolved.json()["resolution_summary"]

    closed = client.post(
        f"/api/v1/incidents/{incident['id']}/status",
        json={"status": "closed", "note": "Verified for 24h"},
        headers=engineer_headers,
    )
    assert closed.status_code == 200
    assert closed.json()["closed_at"]

    detail = client.get(f"/api/v1/incidents/{incident['id']}", headers=engineer_headers).json()
    statuses = [note["status_change"] for note in detail["notes"] if note["status_change"]]
    assert statuses == ["detected", "acknowledged", "investigating", "resolved", "closed"]


def test_incident_notes_and_stats(client, engineer_headers):
    listed = client.get("/api/v1/incidents?page_size=5", headers=engineer_headers).json()
    target = listed["items"][0]
    note = client.post(
        f"/api/v1/incidents/{target['id']}/notes",
        json={"note": "Confirmed mitigation holds.", "note_type": "comment"},
        headers=engineer_headers,
    )
    assert note.status_code == 201
    stats = client.get("/api/v1/incidents/stats", headers=engineer_headers).json()
    assert stats["total"] >= 5
    assert "by_status" in stats


def test_remediation_catalog_only_contains_safe_actions(client, admin_headers):
    catalog = client.get("/api/v1/remediation/catalog", headers=admin_headers).json()
    names = {item["name"] for item in catalog}
    assert "restart_service" in names
    assert "run_health_check" in names
    # destructive cloud operations must not exist at all
    forbidden = {"terminate_instance", "delete_bucket", "modify_iam_policy", "open_security_group", "run_shell"}
    assert names.isdisjoint(forbidden)
    assert all(item["destructive"] is False for item in catalog)


def test_unknown_action_is_rejected(client, engineer_headers):
    response = client.post(
        "/api/v1/remediation/actions",
        json={"action_name": "terminate_instance", "instance_id": 1, "dry_run": True},
        headers=engineer_headers,
    )
    assert response.status_code == 422


def test_dry_run_makes_no_change_and_records_plan(client, engineer_headers, admin_headers):
    instances = client.get("/api/v1/instances", headers=admin_headers).json()
    target = next(item for item in instances if item["source"] == "simulated")
    response = client.post(
        "/api/v1/remediation/actions",
        json={"action_name": "restart_service", "instance_id": target["id"], "dry_run": True},
        headers=engineer_headers,
    )
    assert response.status_code == 201, response.text
    action = response.json()
    assert action["status"] == "dry_run"
    assert "No change was made" in action["output"]


def test_production_action_requires_approval_and_second_approver(client, engineer_headers, admin_headers):
    instances = client.get("/api/v1/instances", headers=admin_headers).json()
    target = next(item for item in instances if item["source"] == "simulated")
    request = client.post(
        "/api/v1/remediation/actions",
        json={"action_name": "restart_service", "instance_id": target["id"], "dry_run": False},
        headers=engineer_headers,
    )
    assert request.status_code == 201
    action = request.json()
    assert action["status"] == "pending_approval"

    # cannot execute before approval
    early = client.post(
        f"/api/v1/remediation/actions/{action['id']}/execute", headers=admin_headers
    )
    assert early.status_code == 409

    # requester cannot approve their own action
    self_approve = client.post(
        f"/api/v1/remediation/actions/{action['id']}/approve", json={}, headers=engineer_headers
    )
    assert self_approve.status_code == 403

    approve = client.post(
        f"/api/v1/remediation/actions/{action['id']}/approve",
        json={"note": "Change approved"},
        headers=admin_headers,
    )
    assert approve.status_code == 200
    assert approve.json()["status"] == "approved"

    executed = client.post(
        f"/api/v1/remediation/actions/{action['id']}/execute", headers=admin_headers
    )
    assert executed.status_code == 200
    body = executed.json()
    assert body["status"] == "succeeded"
    assert "SIMULATED" in body["output"]
    assert body["executed_at"]


def test_rule_creation_validates_action_allowlist(client, engineer_headers):
    bad = client.post(
        "/api/v1/remediation/rules",
        json={"name": "Bad rule", "action_name": "delete_everything", "threshold": 90},
        headers=engineer_headers,
    )
    assert bad.status_code == 422

    good = client.post(
        "/api/v1/remediation/rules",
        json={
            "name": "Restart on memory pressure",
            "metric": "memory_percent",
            "operator": ">",
            "threshold": 88,
            "duration_minutes": 5,
            "action_name": "restart_service",
            "dry_run": True,
        },
        headers=engineer_headers,
    )
    assert good.status_code == 201
    assert good.json()["requires_approval"] is True
