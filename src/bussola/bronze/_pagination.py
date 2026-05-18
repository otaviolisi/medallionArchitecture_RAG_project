"""Generic paginator for any list endpoint of the Chamber API.

The Chamber API always paginates the same way: query params `pagina` and `itens`.
The last page is detected when the number of records returned is less than
`page_size`.
"""

from __future__ import annotations

from typing import Any, Iterator

import httpx

from bussola.bronze._http import get_json
from bussola.logger import get_logger
from bussola.settings import Settings

log = get_logger("bussola.bronze.pagination")

MAX_PAGES_SAFEGUARD = 1000


def paginate(
    client: httpx.Client,
    path: str,
    settings: Settings,
    base_params: dict[str, Any] | None = None,
) -> Iterator[list[dict]]:
    """Yield each page of records until the endpoint is exhausted."""
    base_params = base_params or {}
    page = 1

    while page <= MAX_PAGES_SAFEGUARD:
        params = {**base_params, "pagina": page, "itens": settings.page_size}
        payload = get_json(client, path, settings, params=params)
        records = payload.get("dados", [])

        log.info("  page %d -> %d records", page, len(records))
        yield records

        if len(records) < settings.page_size:
            return
        page += 1

    log.error("pagination safeguard hit (%d pages) for %s", MAX_PAGES_SAFEGUARD, path)
