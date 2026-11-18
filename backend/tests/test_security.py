from __future__ import annotations


def test_findings_are_labelled_by_provenance(client, admin_headers):
    response = client.get("/api/v1/security/findings?status=all&page_size=100", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] > 0
    kinds = {item["source_kind"] for item in body["items"]}
    assert kinds.issubset({"simulated", "aws", "tool", "rule-engine"})
    # simulation must be explicit in the payload
    simulated = [item for item in body["items"] if item["source_kind"] == "simulated"]
    assert simulated
    assert all("simulated" in item["description"].lower() for item in simulated)


def test_open_ssh_finding_detected(client, admin_headers):
    body = client.get(
        "/api/v1/security/findings?status=open&severity=critical&page_size=100", headers=admin_headers
    ).json()
    titles = " ".join(item["title"] for item in body["items"])
    assert "SSH" in titles or "RDP" in titles


def test_scan_runs_and_reports_tool_outcomes(client, engineer_headers):
    response = client.post(
        "/api/v1/security/scan",
        json={"tools": ["rules", "aws"], "include_cloud": True},
        headers=engineer_headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["scan_id"]
    assert body["simulated_resources"] is True
    statuses = {tool["tool"]: tool["status"] for tool in body["tools"]}
    assert statuses["aws-config-audit"] == "executed"
    assert statuses["sentinel-iac-rules"] == "executed"


def test_unavailable_tool_is_reported_not_fabricated(client, engineer_headers):
    response = client.post(
        "/api/v1/security/scan",
        json={"tools": ["trivy"], "include_cloud": False},
        headers=engineer_headers,
    )
    assert response.status_code == 200
    tool = response.json()["tools"][0]
    assert tool["tool"] == "trivy"
    assert tool["status"] in {"skipped", "failed"}
    assert tool["findings"] == 0


def test_reports_are_downloadable(client, admin_headers):
    json_report = client.get("/api/v1/security/report?format=json", headers=admin_headers)
    assert json_report.status_code == 200
    assert json_report.headers["content-type"].startswith("application/json")
    payload = json_report.json()
    assert payload["product"] == "CloudOps Sentinel"
    assert isinstance(payload["findings"], list)

    csv_report = client.get("/api/v1/security/report?format=csv", headers=admin_headers)
    assert csv_report.status_code == 200
    assert "text/csv" in csv_report.headers["content-type"]
    assert "finding_id" in csv_report.text.splitlines()[0]


def test_finding_status_update(client, engineer_headers):
    findings = client.get("/api/v1/security/findings?status=open", headers=engineer_headers).json()
    target = findings["items"][0]
    response = client.patch(
        f"/api/v1/security/findings/{target['id']}", json={"status": "acknowledged"}, headers=engineer_headers
    )
    assert response.status_code == 200
    assert response.json()["status"] == "acknowledged"


def test_security_summary_risk_score(client, admin_headers):
    body = client.get("/api/v1/security/summary", headers=admin_headers).json()
    assert 0 <= body["risk_score"] <= 100
    assert body["counts"]["critical"] >= 1
