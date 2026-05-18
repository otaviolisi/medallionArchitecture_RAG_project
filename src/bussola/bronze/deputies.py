"""Bronze extractor for the /deputados endpoint.

Strategy:
- Fetch the paginated list of deputies (summary records).
- For each summary, follow `uri` to fetch the full detail record.
- Merge summary + detail into a single enriched record per deputy.
- Save the whole snapshot as one JSON file named by today's date.

Re-run behavior:
- Always re-runs (a snapshot is meant to reflect "right now").
- Each run appends an entry to `snapshots_history` in state.json,
  building an audit trail of when each snapshot was taken.
- Two runs on the same day will produce the same file name and
  overwrite it; the history list will contain both entries.
"""

from __future__ import annotations

import time
from datetime import date

from bussola.bronze._http import get_json, make_client
from bussola.bronze._pagination import paginate
from bussola.bronze._writer import write_json
from bussola.logger import get_logger
from bussola.settings import load_settings
from bussola.state import load_state, record_snapshot, save_state

log = get_logger("bussola.bronze.deputies")

ENDPOINT_NAME = "deputies"
LIST_PATH = "/deputados"


def _build_record(summary: dict, detail: dict) -> dict:
    """Combine the summary record with its full detail.

    Bronze rule: keep ALL fields. The two payloads are preserved under
    `summary` and `detail` keys to make provenance explicit and avoid
    name collisions (the same field can appear in both with different values).
    """
    return {
        "id": summary["id"],
        "summary": summary,
        "detail": detail,
    }


def extract(limit: int | None = None) -> None:
    """Run the deputies snapshot extraction.

    Args:
        limit: cap the number of deputies fan-out (smoke testing). None = all.
    """
    settings = load_settings()
    state = load_state()

    log.info("=" * 60)
    log.info("deputies extraction starting (limit=%s)", limit or "none")
    log.info("=" * 60)

    enriched_records: list[dict] = []

    with make_client(settings) as client:
        # 1) Fetch the full paginated list of summaries
        list_params = {"ordem": "ASC", "ordenarPor": "nome"}
        summaries: list[dict] = []
        for page_records in paginate(client, LIST_PATH, settings, list_params):
            summaries.extend(page_records)

        log.info("collected %d deputy summaries", len(summaries))

        if limit:
            summaries = summaries[:limit]
            log.info("limit applied: fan-out for %d deputies", len(summaries))

        # 2) Fan-out: fetch detail for each summary by following its `uri`
        total = len(summaries)
        for idx, summary in enumerate(summaries, start=1):
            log.info("[%d/%d] fetching detail for %s", idx, total, summary["nome"])
            detail_payload = get_json(client, summary["uri"], settings)
            detail = detail_payload.get("dados", {})
            enriched_records.append(_build_record(summary, detail))
            time.sleep(settings.request_delay_seconds)

    # 3) Save snapshot file and record in state history
    file_name = f"snapshot_{date.today().isoformat()}"
    write_json(ENDPOINT_NAME, file_name, enriched_records)

    ids = [r["id"] for r in enriched_records]
    record_snapshot(state, ENDPOINT_NAME, ids, file_name=f"{file_name}.json")
    save_state(state)

    log.info("deputies extraction complete: %d records saved", len(enriched_records))


if __name__ == "__main__":
    # Allows `python -m bussola.bronze.deputies` as an alternative to the script
    extract()
