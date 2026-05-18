"""Shared HTTP client used by all bronze extractors.

Provides a configured httpx.Client and a `get_json` helper that:
- Retries on 5xx, 429, timeouts, and network errors (transient errors)
- Fails fast on other 4xx (client error - retry won't help)
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from bussola.logger import get_logger
from bussola.settings import Settings

log = get_logger("bussola.bronze.http")

USER_AGENT = "bussola-publica/0.1 (data-engineering portfolio)"

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def make_client(settings: Settings) -> httpx.Client:
    """Create a configured HTTP client. Caller is responsible for closing it."""
    return httpx.Client(
        base_url=settings.base_url,
        timeout=settings.timeout_seconds,
        headers={
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )


def get_json(
    client: httpx.Client,
    url_or_path: str,
    settings: Settings,
    params: dict[str, Any] | None = None,
) -> dict:
    """GET a URL (relative path or absolute) and return parsed JSON."""
    last_exc: Exception | None = None

    for attempt in range(1, settings.max_retries + 1):
        try:
            response = client.get(url_or_path, params=params)

            # 4xx that is not 429: client error, do not retry
            if 400 <= response.status_code < 500 and response.status_code != 429:
                log.error(
                    "client error %d for %s - not retrying. body: %s",
                    response.status_code,
                    url_or_path,
                    response.text[:200],
                )
                response.raise_for_status()

            # 5xx and 429: retryable
            if response.status_code in RETRYABLE_STATUS_CODES:
                raise httpx.HTTPStatusError(
                    f"retryable status {response.status_code}",
                    request=response.request,
                    response=response,
                )

            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as e:
            if e.response.status_code < 500 and e.response.status_code != 429:
                raise
            last_exc = e
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            last_exc = e

        if attempt == settings.max_retries:
            break

        wait = settings.retry_backoff_seconds * (2 ** (attempt - 1))
        log.warning(
            "attempt %d/%d failed for %s (%s) - sleeping %ds",
            attempt, settings.max_retries, url_or_path, last_exc, wait,
        )
        time.sleep(wait)

    raise RuntimeError(
        f"GET {url_or_path} failed after {settings.max_retries} attempts: {last_exc}"
    )
