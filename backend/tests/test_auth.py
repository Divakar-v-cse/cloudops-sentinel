from __future__ import annotations


def test_health_is_public(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"


def test_protected_endpoint_requires_token(client):
    response = client.get("/api/v1/dashboard/overview")
    assert response.status_code == 401


def test_login_rejects_bad_password(client):
    response = client.post(
        "/api/v1/auth/login", json={"email": "admin@cloudops.local", "password": "wrong-password"}
    )
    assert response.status_code == 401


def test_login_and_identity(client, admin_headers):
    me = client.get("/api/v1/auth/me", headers=admin_headers)
    assert me.status_code == 200
    body = me.json()
    assert body["email"] == "admin@cloudops.local"
    assert body["role"] == "admin"


def test_role_enforcement(client, engineer_headers):
    # engineer cannot change thresholds (admin only)
    response = client.patch(
        "/api/v1/monitoring/thresholds/cpu_percent",
        json={"warning": 65},
        headers=engineer_headers,
    )
    assert response.status_code == 403


def test_admin_can_create_user(client, admin_headers):
    payload = {
        "email": "viewer-test@cloudops.local",
        "full_name": "Viewer Test",
        "password": "Viewer@12345",
        "role": "viewer",
    }
    response = client.post("/api/v1/auth/users", json=payload, headers=admin_headers)
    assert response.status_code == 201, response.text
    assert response.json()["role"] == "viewer"

    duplicate = client.post("/api/v1/auth/users", json=payload, headers=admin_headers)
    assert duplicate.status_code == 409
