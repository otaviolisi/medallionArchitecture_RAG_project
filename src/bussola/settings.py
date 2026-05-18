"""Loads shared settings from config/settings.yaml + .env."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

CONFIG_PATH = Path("config/settings.yaml")


@dataclass(frozen=True)
class Settings:
    base_url: str
    timeout_seconds: int
    page_size: int
    max_retries: int
    retry_backoff_seconds: int
    request_delay_seconds: float


def load_settings() -> Settings:
    """Load YAML settings with environment overrides for sensitive fields."""
    with CONFIG_PATH.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    api = raw["api"]
    http = raw["http"]

    return Settings(
        base_url=os.getenv("CAMARA_API_BASE_URL", api["base_url"]),
        timeout_seconds=api["timeout_seconds"],
        page_size=api["page_size"],
        max_retries=http["max_retries"],
        retry_backoff_seconds=http["retry_backoff_seconds"],
        request_delay_seconds=http["request_delay_seconds"],
    )
