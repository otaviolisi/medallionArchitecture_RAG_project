"""Bronze extractor for the /votacoes endpoint.

Strategy:
- Query the API for a date window ending today. The window's start is:
    * The high-water mark's date if state.json already has one.
    * `today - months*30` on the first run (or when state is lost).
- Paginate the list (no fan-out — the list payload already contains
  everything we need: id, descricao, aprovacao, proposicaoObjeto, etc.).
- Filter records to keep only those with `dataHoraRegistro` strictly greater
  than `state.votings.last_data_hora_registro`. This catches any records
  of the watermark's day that are already known.
- Save those "new" records as a delta file named by the run timestamp.
- Update the high-water mark in state.

Re-run behavior:
- Always re-runs (each execution checks the API for newer events).
- Each run appends an entry to `deltas_history` in state.json.
- A delta file with zero new records is still written for audit purposes
  (so the history reflects every execution, not only the ones that found
  data).

KNOWN LIMITATION - late-arriving records:
The high-water mark is the maximum `dataHoraRegistro` seen so far.
If the Chamber later registers a voting whose `dataHoraRegistro` is
older than the current high-water mark (e.g. a session retroactively
entered), this extractor will MISS that record. This is an accepted
trade-off in exchange for the simplicity of timestamp-based watermarking.
A future iteration may switch to ID-based deduplication or a hybrid
approach to close this gap.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from bussola.bronze._http import make_client
from bussola.bronze._pagination import paginate
from bussola.bronze._writer import write_json
from bussola.logger import get_logger
from bussola.settings import load_settings
from bussola.state import load_state, record_delta, save_state

log = get_logger("bussola.bronze.votings")

ENDPOINT_NAME = "votings"
LIST_PATH = "/votacoes"
DEFAULT_WINDOW_MONTHS = 3


def _compute_window(months: int, high_water_mark: str | None) -> tuple[date, date]:
    """Compute the API search window.

    If a high-water mark exists, the window starts on its date (we only need
    to ask the API about events from that day onward). Otherwise it falls
    back to the wide `months`-month window (first run, or state.json lost).

    The watermark is an ISO timestamp like "2026-05-18T14:30:00";
    we extract just the date part because the API only filters by day.
    """
    end = date.today()

    if high_water_mark:
        watermark_date = date.fromisoformat(high_water_mark[:10])
        # Re-query from the watermark day forward. Records of that same day
        # that are already known are still filtered out in _filter_new_records.
        start = watermark_date
    else:
        start = end - timedelta(days=months * 30)

    return start, end


def _filter_new_records(records: list[dict], high_water_mark: str | None) -> list[dict]:
    """Keep only records whose dataHoraRegistro is strictly greater than
    the previous high-water mark.

    On the first run (no high-water mark yet), all records are considered new.
    """
    if high_water_mark is None:
        return records
    return [r for r in records if r.get("dataHoraRegistro", "") > high_water_mark]


def _max_data_hora_registro(records: list[dict]) -> str | None:
    """Return the maximum dataHoraRegistro across the given records.

    Returns None when records is empty.
    """
    if not records:
        return None
    return max((r.get("dataHoraRegistro", "") for r in records), default=None) or None


def _utc_now_compact() -> str:
    """Compact UTC timestamp safe for file names: 20260518T093045Z."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def extract(months: int = DEFAULT_WINDOW_MONTHS) -> None:
    """Run an incremental extraction of votings.

    Args:
        months: width of the search window in months ending today.
            Default = 3, as defined by the project requirements.
    """
    settings = load_settings()
    state = load_state()

    high_water_mark = state.get(ENDPOINT_NAME, {}).get("last_data_hora_registro")
    window_start, window_end = _compute_window(months, high_water_mark)

    log.info("=" * 60)
    log.info(
        "votings extraction: window %s -> %s (high_water_mark=%s)",
        window_start, window_end, high_water_mark or "<first run>",
    )
    log.info("=" * 60)

    # 1) Paginated list call for the full 3-month window (no fan-out)
    list_params = {
        "dataInicio": window_start.isoformat(),
        "dataFim": window_end.isoformat(),
        "ordem": "ASC",
        "ordenarPor": "dataHoraRegistro",
    }

    all_records: list[dict] = []
    with make_client(settings) as client:
        for page_records in paginate(client, LIST_PATH, settings, list_params):
            all_records.extend(page_records)

    log.info("API returned %d records in window", len(all_records))

    # 2) Filter against the high-water mark
    new_records = _filter_new_records(all_records, high_water_mark)
    log.info(
        "filtered to %d new records (skipped %d already-known)",
        len(new_records), len(all_records) - len(new_records),
    )

    # 3) Write delta file (always, even when empty - for audit trail)
    file_name = f"delta_{_utc_now_compact()}"
    write_json(ENDPOINT_NAME, file_name, new_records)

    # 4) Compute the new high-water mark
    new_hwm_candidate = _max_data_hora_registro(new_records)
    if new_hwm_candidate and (high_water_mark is None or new_hwm_candidate > high_water_mark):
        new_high_water_mark = new_hwm_candidate
    else:
        new_high_water_mark = high_water_mark  # unchanged

    # 5) Update state
    previous_total = state.get(ENDPOINT_NAME, {}).get("total_records_known", 0)
    record_delta(
        state=state,
        endpoint=ENDPOINT_NAME,
        file_name=f"{file_name}.json",
        new_records=len(new_records),
        total_records_known=previous_total + len(new_records),
        window_start=window_start.isoformat(),
        window_end=window_end.isoformat(),
        last_data_hora_registro=new_high_water_mark,
    )
    save_state(state)

    log.info(
        "votings extraction complete: %d new records (HWM now=%s)",
        len(new_records), new_high_water_mark or "<unchanged>",
    )


if __name__ == "__main__":
    extract()