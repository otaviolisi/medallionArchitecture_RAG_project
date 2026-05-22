"""Bronze extractor for the /proposicoes endpoint.

Strategy:
- First run: fetch DEFAULT_WINDOW_MONTHS (12) of data, split into 90-day
  chunks (API limitation on date range per call). Fan-out each result.
- Incremental runs: single window from the HWM date to today (typically a
  few days — no chunking needed unless the run is delayed > 3 months).
- For each proposition: follow `uri` for full detail. Merge as
  {id, summary, detail} — schema stays dynamic (bronze keeps ALL fields).
- Filter against the HWM (`dataApresentacao`) to skip already-known records.
- Write one delta file per run; always written even when empty (audit trail).

API notes:
- Date params: `dataApresentacaoInicio`, `dataApresentacaoFim` (YYYY-MM-DD).
- `dataApresentacao` in results: "2026-04-01T08:19" (no seconds, no tz).
- Detail schema varies per proposition type — intentional, not a bug.

Known limitation (same trade-off as votings):
- Propositions filed retroactively with a `dataApresentacao` older than the
  current HWM will be missed. Accepted in exchange for simplicity.
"""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta, timezone

from bussola.bronze._http import get_json, make_client
from bussola.bronze._pagination import paginate
from bussola.bronze._writer import write_json
from bussola.logger import get_logger
from bussola.settings import load_settings
from bussola.state import load_state, record_delta, save_state

log = get_logger("bussola.bronze.propositions")

ENDPOINT_NAME = "propositions"
LIST_PATH = "/proposicoes"
DEFAULT_WINDOW_MONTHS = 12
API_MAX_CHUNK_DAYS = 90  # ~3 months; API rejects wider date windows


def _build_record(summary: dict, detail: dict) -> dict:
    return {
        "id": summary["id"],
        "summary": summary,
        "detail": detail,
    }


def _date_chunks(start: date, end: date) -> list[tuple[date, date]]:
    """Split [start, end] into non-overlapping windows of at most API_MAX_CHUNK_DAYS.

    Consecutive windows are adjacent (end + 1 day = next start) to avoid
    duplicates, assuming the API's date filters are inclusive on both ends.
    """
    chunks = []
    cursor = start
    while cursor <= end:
        chunk_end = min(cursor + timedelta(days=API_MAX_CHUNK_DAYS), end)
        chunks.append((cursor, chunk_end))
        if chunk_end >= end:
            break
        cursor = chunk_end + timedelta(days=1)
    return chunks


def _compute_start(high_water_mark: str | None, default_months: int) -> date:
    if high_water_mark:
        return date.fromisoformat(high_water_mark[:10])
    return date.today() - timedelta(days=default_months * 30)


def _filter_new(records: list[dict], high_water_mark: str | None) -> list[dict]:
    """Keep only records with dataApresentacao strictly greater than HWM."""
    if high_water_mark is None:
        return records
    return [r for r in records if r.get("dataApresentacao", "") > high_water_mark]


def _max_data_apresentacao(enriched: list[dict]) -> str | None:
    """Return max dataApresentacao from enriched {id, summary, detail} records."""
    if not enriched:
        return None
    values = [
        r["summary"].get("dataApresentacao", "")
        for r in enriched
        if r.get("summary", {}).get("dataApresentacao")
    ]
    return max(values) if values else None


def _utc_now_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def extract(months: int = DEFAULT_WINDOW_MONTHS, limit: int | None = None) -> None:
    """Run an incremental extraction of propositions with fan-out per record.

    Args:
        months: width of the initial backfill window in months. Default = 12.
        limit: cap total fan-out calls (smoke testing). None = all.
            With limit, the HWM only advances to the last processed record.
    """
    settings = load_settings()
    state = load_state()

    high_water_mark = state.get(ENDPOINT_NAME, {}).get("last_data_hora_registro")
    start = _compute_start(high_water_mark, months)
    end = date.today()
    chunks = _date_chunks(start, end)

    log.info("=" * 60)
    log.info(
        "propositions extraction: %s -> %s in %d chunk(s) (HWM=%s)",
        start, end, len(chunks), high_water_mark or "<first run>",
    )
    log.info("=" * 60)

    all_summaries: list[dict] = []
    with make_client(settings) as client:
        # 1) Collect summaries across all date chunks
        for chunk_start, chunk_end in chunks:
            if limit and len(all_summaries) >= limit:
                break
            log.info("  chunk %s -> %s", chunk_start, chunk_end)
            params = {
                "dataApresentacaoInicio": chunk_start.isoformat(),
                "dataApresentacaoFim": chunk_end.isoformat(),
                "ordem": "ASC",
                "ordenarPor": "id",
            }
            for page_records in paginate(client, LIST_PATH, settings, params):
                all_summaries.extend(page_records)
                if limit and len(all_summaries) >= limit:
                    break

        log.info("collected %d proposition summaries", len(all_summaries))

        # 2) Filter against HWM — skip anything already processed
        new_summaries = _filter_new(all_summaries, high_water_mark)
        log.info(
            "filtered to %d new summaries (skipped %d already-known)",
            len(new_summaries), len(all_summaries) - len(new_summaries),
        )

        if limit:
            new_summaries = new_summaries[:limit]
            log.info("limit applied: fan-out capped at %d", len(new_summaries))

        # 3) Fan-out: fetch full detail per proposition
        enriched: list[dict] = []
        total = len(new_summaries)
        for idx, summary in enumerate(new_summaries, start=1):
            log.info(
                "[%d/%d] %s %s/%s",
                idx, total,
                summary.get("siglaTipo", "?"),
                summary.get("numero", "?"),
                summary.get("ano", "?"),
            )
            detail_payload = get_json(client, summary["uri"], settings)
            detail = detail_payload.get("dados", {})
            enriched.append(_build_record(summary, detail))
            time.sleep(settings.request_delay_seconds)

    # 4) Write delta file (always — audit trail)
    file_name = f"delta_{_utc_now_compact()}"
    write_json(ENDPOINT_NAME, file_name, enriched)

    # 5) Advance HWM only to what was actually fanned-out (handles --limit correctly)
    new_hwm_candidate = _max_data_apresentacao(enriched)
    if new_hwm_candidate and (high_water_mark is None or new_hwm_candidate > high_water_mark):
        new_high_water_mark = new_hwm_candidate
    else:
        new_high_water_mark = high_water_mark

    previous_total = state.get(ENDPOINT_NAME, {}).get("total_records_known", 0)
    record_delta(
        state=state,
        endpoint=ENDPOINT_NAME,
        file_name=f"{file_name}.json",
        new_records=len(enriched),
        total_records_known=previous_total + len(enriched),
        window_start=start.isoformat(),
        window_end=end.isoformat(),
        last_data_hora_registro=new_high_water_mark,
    )
    save_state(state)

    log.info(
        "propositions extraction complete: %d new records (HWM now=%s)",
        len(enriched), new_high_water_mark or "<unchanged>",
    )


if __name__ == "__main__":
    extract()