"""Idempotency / history state for bronze extractors.

State file shape:
{
  "deputies": {                                  // snapshot endpoints
    "last_snapshot": "2026-05-14",
    "ids_known": [123, 124, ...],
    "last_run": "2026-05-14T18:30:12+00:00",
    "snapshots_history": [
      {"date": "...", "count": 513, "file": "...", "ran_at": "..."},
      ...
    ]
  },
  "votings": {                                   // incremental endpoints
    "last_data_hora_registro": "2026-05-19T11:30:00",
    "total_records_known": 203,
    "last_run": "2026-05-19T09:30:00+00:00",
    "deltas_history": [
      {"file": "...", "ran_at": "...", "new_records": 3,
       "window_start": "...", "window_end": "..."},
      ...
    ]
  }
}
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

STATE_FILE = Path("data/bronze/_state.json")


def load_state() -> dict:
    """Load state.json. Returns empty dict if missing."""
    if not STATE_FILE.exists():
        return {}
    with STATE_FILE.open(encoding="utf-8") as f:
        return json.load(f)


def save_state(state: dict) -> None:
    """Persist state.json atomically (write to tmp file, then rename)."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2, sort_keys=True)
    tmp.replace(STATE_FILE)


def record_snapshot(
    state: dict,
    endpoint: str,
    ids: list[int],
    file_name: str,
) -> None:
    """Record the result of a snapshot run.

    Appends an entry to `snapshots_history` (audit trail) and updates the
    "current" pointer fields (`last_snapshot`, `ids_known`, `last_run`).
    """
    ep = state.setdefault(endpoint, {})

    today = datetime.now(timezone.utc).date().isoformat()
    now_iso = datetime.now(timezone.utc).isoformat()

    history = ep.get("snapshots_history", [])
    history.append(
        {
            "date": today,
            "count": len(ids),
            "file": file_name,
            "ran_at": now_iso,
        }
    )

    ep["snapshots_history"] = history
    ep["last_snapshot"] = today
    ep["ids_known"] = sorted(set(ids))
    ep["last_run"] = now_iso


def record_delta(
    state: dict,
    endpoint: str,
    file_name: str,
    new_records: int,
    total_records_known: int,
    window_start: str,
    window_end: str,
    last_data_hora_registro: str | None,
) -> None:
    """Record the result of an incremental (delta) run.

    Used by event-style endpoints (e.g. votings) where each run captures
    only what is new since the previous high-water mark.

    Args:
        state: state dict (mutated in place).
        endpoint: endpoint key under which to record.
        file_name: name of the delta JSON file written for this run.
        new_records: count of records considered new in this run.
        total_records_known: cumulative count after this run.
        window_start: ISO date string - start of the API search window.
        window_end: ISO date string - end of the API search window.
        last_data_hora_registro: most recent dataHoraRegistro across all
            records known so far (high-water mark for the next run).
    """
    ep = state.setdefault(endpoint, {})
    now_iso = datetime.now(timezone.utc).isoformat()

    history = ep.get("deltas_history", [])
    history.append(
        {
            "file": file_name,
            "ran_at": now_iso,
            "new_records": new_records,
            "window_start": window_start,
            "window_end": window_end,
        }
    )

    ep["deltas_history"] = history
    ep["total_records_known"] = total_records_known
    ep["last_run"] = now_iso
    if last_data_hora_registro is not None:
        ep["last_data_hora_registro"] = last_data_hora_registro