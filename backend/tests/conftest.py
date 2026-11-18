from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

TEST_DB = Path(tempfile.gettempdir()) / "cloudops_sentinel_test.db"
if TEST_DB.exists():
    TEST_DB.unlink()

os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["ENABLE_SCHEDULER"] = "false"
os.environ["SECRET_KEY"] = "test-only-secret-key"
os.environ["ENVIRONMENT"] = "test"
os.environ["AWS_SIMULATION_MODE"] = "true"
os.environ["AI_PROVIDER"] = "none"
os.environ["DEFAULT_ADMIN_PASSWORD"] = "TestAdmin@12345"
os.environ["DEFAULT_ANALYST_PASSWORD"] = "TestAnalyst@12345"

from fastapi.testclient import TestClient  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.services.bootstrap import bootstrap, init_db  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def prepared_database():
    init_db()
    db = SessionLocal()
    try:
        bootstrap(db)
    finally:
        db.close()
    yield


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app)


def _login(client: TestClient, email: str, password: str) -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest.fixture(scope="session")
def admin_token(client: TestClient) -> str:
    return _login(client, "admin@cloudops.local", "TestAdmin@12345")


@pytest.fixture(scope="session")
def engineer_token(client: TestClient) -> str:
    return _login(client, "engineer@cloudops.local", "TestAdmin@12345")


@pytest.fixture(scope="session")
def admin_headers(admin_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="session")
def engineer_headers(engineer_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {engineer_token}"}
