"""Application configuration.

All configuration is environment driven. Nothing secret is hardcoded:
the development defaults below are non-sensitive placeholders and are
flagged in logs/startup output when they are still in use.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REPO_ROOT = os.path.dirname(BASE_DIR)


class Settings(BaseSettings):
    # ``../.env`` lets a single repository-level .env drive both services while
    # ``.env`` in the working directory still overrides it for the API process.
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    # --- application -------------------------------------------------
    app_name: str = "CloudOps Sentinel"
    app_version: str = "1.0.0"
    environment: str = Field(default="local", description="local | staging | production")
    debug: bool = False
    api_prefix: str = "/api/v1"

    # --- security ----------------------------------------------------
    secret_key: str = "dev-only-insecure-secret-change-me"
    access_token_expire_minutes: int = 480
    algorithm: str = "HS256"
    default_admin_email: str = "admin@cloudops.local"
    default_admin_password: str = "Admin@12345"
    default_analyst_password: str = "Analyst@12345"

    # --- database ----------------------------------------------------
    database_url: str = f"sqlite:///{os.path.join(BASE_DIR, 'cloudops.db')}"
    sql_echo: bool = False

    # --- cache / queue ----------------------------------------------
    redis_url: str | None = None

    # --- monitoring --------------------------------------------------
    monitoring_interval_seconds: int = 15
    monitoring_history_retention_hours: int = 72
    enable_scheduler: bool = True
    enable_local_collector: bool = True

    # --- thresholds defaults (persisted rows override) ---------------
    cpu_warning: float = 70.0
    cpu_critical: float = 90.0
    memory_warning: float = 75.0
    memory_critical: float = 92.0
    disk_warning: float = 80.0
    disk_critical: float = 93.0
    network_warning_kbps: float = 80_000.0
    network_critical_kbps: float = 150_000.0

    # --- AWS ---------------------------------------------------------
    aws_region: str = Field(default_factory=lambda: os.getenv("AWS_REGION", "us-east-1"))
    aws_profile: str | None = None
    aws_simulation_mode: bool = True  # safe default: never touch real AWS until enabled
    aws_connect_timeout: int = 5
    sns_topic_arn: str | None = None

    # --- costs -------------------------------------------------------
    cost_budget_usd: float = 3000.0
    cost_hours_per_month: int = 730
    cost_idle_cpu_threshold: float = 5.0
    cost_currency: str = "USD"

    # --- logs --------------------------------------------------------
    log_retention_days: int = 14
    max_ingest_batch: int = 500

    # --- AI (optional, never required) ------------------------------
    ai_provider: str = "none"  # none | openai-compatible
    ai_api_key: str | None = None
    ai_base_url: str = "https://api.openai.com/v1"
    ai_model: str = "gpt-4o-mini"
    ai_timeout_seconds: int = 20

    # --- CORS --------------------------------------------------------
    cors_origins: List[str] = ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:4173"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value):
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def ai_enabled(self) -> bool:
        return self.ai_provider != "none" and bool(self.ai_api_key)

    @property
    def insecure_defaults(self) -> list[str]:
        warnings: list[str] = []
        if self.secret_key.startswith("dev-only"):
            warnings.append("SECRET_KEY is the development default")
        if self.environment == "production" and self.default_admin_password == "Admin@12345":
            warnings.append("Default admin password is still enabled")
        return warnings


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
