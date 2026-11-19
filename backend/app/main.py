"""CloudOps Sentinel API entrypoint."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.router import api_router
from app.core.config import settings
from app.core.utils import iso, utcnow
from app.db.session import SessionLocal, engine
from app.schemas.common import HealthResponse
from app.services import aws as aws_service
from app.services import bootstrap as bootstrap_service
from app.services import monitoring
from app.services import remediation as remediation_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("cloudops.sentinel")

async def _scheduler_loop(stop: asyncio.Event) -> None:
    """Collect telemetry, evaluate remediation rules and prune history."""
    interval = max(settings.monitoring_interval_seconds, 5)
    backoff = interval
    while not stop.is_set():
        try:
            await asyncio.to_thread(_collect_once)
            backoff = interval
        except Exception:  # pragma: no cover - keep the loop alive
            logger.exception("Monitoring cycle failed; retrying in %ss", backoff)
            backoff = min(backoff * 2, 300)
        try:
            await asyncio.wait_for(stop.wait(), timeout=backoff)
        except asyncio.TimeoutError:
            continue


def _collect_once() -> None:
    db = SessionLocal()
    try:
        result = monitoring.collect_all(db)
        remediation_service.evaluate_rules(db)
        if result["errors"]:
            logger.warning("Collection issues: %s", result["errors"])
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s %s (%s)", settings.app_name, settings.app_version, settings.environment)
    for warning in settings.insecure_defaults:
        logger.warning("SECURITY: %s", warning)

    bootstrap_service.init_db()
    db = SessionLocal()
    try:
        bootstrap_service.bootstrap(db)
    except Exception:  # pragma: no cover - startup must not hard fail on seed issues
        logger.exception("Bootstrap encountered an error; continuing with existing data")
    finally:
        db.close()

    stop = asyncio.Event()
    task = None
    if settings.enable_scheduler:
        task = asyncio.create_task(_scheduler_loop(stop))
    app.state.stop_scheduler = stop
    yield
    stop.set()
    if task is not None:
        try:
            await asyncio.wait_for(task, timeout=5)
        except asyncio.TimeoutError:  # pragma: no cover
            task.cancel()
    logger.info("Sentinel stopped")


app = FastAPI(
    title=f"{settings.app_name} API",
    version=settings.app_version,
    description=(
        "AI-assisted AWS monitoring, security, cost, incident and remediation platform.\n\n"
        "Default deployment runs in **local mode**: SQLite + psutil host metrics + a clearly "
        "labelled simulated fleet. AWS access is optional and read-only."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):  # pragma: no cover
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/", tags=["meta"])
def root() -> dict:
    return {
        "product": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "api": settings.api_prefix,
        "mode": "local" if settings.environment == "local" else settings.environment,
        "aws": aws_service.connection_status()["mode"],
    }


@app.get("/api/v1/health", tags=["meta"], response_model=HealthResponse, include_in_schema=False)
def api_health() -> HealthResponse:
    """Same probe as ``/health``, mounted under the prefix the SPA's client uses."""
    return health()


@app.get("/health", tags=["meta"], response_model=HealthResponse)
def health() -> HealthResponse:
    database = "ok"
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover
        database = f"error: {exc}"
    return HealthResponse(
        status="ok" if database == "ok" else "degraded",
        version=settings.app_version,
        environment=settings.environment,
        mode="local",
        database=database,
        scheduler=settings.enable_scheduler,
        aws_configured=aws_service.connection_status()["mode"] == "connected",
        ai_enabled=settings.ai_enabled,
        server_time=iso(utcnow()),
    )


@app.get("/metrics", tags=["meta"], include_in_schema=False)
def prometheus_metrics() -> str:
    """Minimal Prometheus exposition built from live counters."""
    from app.models import Incident, InfrastructureInstance, Metric, SecurityFinding

    db = SessionLocal()
    try:
        instances = db.query(InfrastructureInstance).count()
        running = db.query(InfrastructureInstance).filter(InfrastructureInstance.status == "running").count()
        critical = (
            db.query(Incident)
            .filter(Incident.status.in_(["detected", "acknowledged", "investigating"]), Incident.severity == "critical")
            .count()
        )
        findings = db.query(SecurityFinding).filter(SecurityFinding.status == "open").count()
        samples = db.query(Metric).count()
    finally:
        db.close()
    lines = [
        "# HELP sentinel_instances_total Inventory rows",
        "# TYPE sentinel_instances_total gauge",
        f"sentinel_instances_total {instances}",
        "# HELP sentinel_instances_running Running instances",
        "# TYPE sentinel_instances_running gauge",
        f"sentinel_instances_running {running}",
        "# HELP sentinel_incidents_critical_open Open critical incidents",
        "# TYPE sentinel_incidents_critical_open gauge",
        f"sentinel_incidents_critical_open {critical}",
        "# HELP sentinel_findings_open Open security findings",
        "# TYPE sentinel_findings_open gauge",
        f"sentinel_findings_open {findings}",
        "# HELP sentinel_metric_samples Stored telemetry samples",
        "# TYPE sentinel_metric_samples gauge",
        f"sentinel_metric_samples {samples}",
    ]
    return "\n".join(lines) + "\n"
