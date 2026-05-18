"""Bronze extractor for the /partidos endpoint.

Strategy:
- Fetch the paginated list of parties (summary records).
- For each summary, follow `uri` to fetch the full detail record.
- Merge summary + detail into a single enriched record per party.
- Save the whole snapshot as one JSON file named by today's date.

Re-run behavior:
- Always re-runs (a snapshot is meant to reflect "right now").
- Each run appends an entry to `snapshots_history` in state.json.

Notes on the data:
- Parties are NOT filtered by status: this snapshot includes active AND
  inactive parties so we can support historical analysis later.
- Parties do not have a UF of their own (they are national). The `uf` field
  visible in the detail payload belongs to the party's current leader,
  accessible at `detail.status.lider.uf`. Field renaming and flattening
  happens in silver, not here.
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

log = get_logger("bussola.bronze.parties")

ENDPOINT_NAME = "parties"
LIST_PATH = "/partidos"


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
    """Run the parties snapshot extraction.

    Args:
        limit: cap the number of parties fanned out (smoke testing). None = all.
    """
    settings = load_settings()
    state = load_state()

    log.info("=" * 60)
    log.info("parties extraction starting (limit=%s)", limit or "none")
    log.info("=" * 60)

    enriched_records: list[dict] = []

    with make_client(settings) as client:
        # 1) Fetch the full paginated list of summaries (active + inactive)
        list_params = {"ordem": "ASC", "ordenarPor": "sigla"}
        summaries: list[dict] = []
        for page_records in paginate(client, LIST_PATH, settings, list_params):
            summaries.extend(page_records)

        log.info("collected %d party summaries", len(summaries))

        if limit:
            summaries = summaries[:limit]
            log.info("limit applied: fan-out for %d parties", len(summaries))

        # 2) Fan-out: fetch detail for each summary by following its `uri`
        total = len(summaries)
        for idx, summary in enumerate(summaries, start=1):
            log.info("[%d/%d] fetching detail for %s", idx, total, summary["sigla"])
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

    log.info("parties extraction complete: %d records saved", len(enriched_records))


if __name__ == "__main__":
    extract()