from fastapi import APIRouter

from app.api.routes import (
    auth,
    aws,
    costs,
    deployments,
    incidents,
    instances,
    logs,
    monitoring,
    platform,
    remediation,
    security,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(instances.router)
api_router.include_router(monitoring.router)
api_router.include_router(security.router)
api_router.include_router(costs.router)
api_router.include_router(logs.router)
api_router.include_router(incidents.router)
api_router.include_router(remediation.router)
api_router.include_router(deployments.router)
api_router.include_router(aws.router)
api_router.include_router(platform.router)
