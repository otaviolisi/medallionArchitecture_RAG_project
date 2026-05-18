"""Idempotency / history state for bronze extractors.

For now, this module only exposes what `deputies` needs.
Other endpoints will extend it with their own helpers when added.

State file shape:
{
  "deputies": {
    "last_snapshot": "2026-05-14",
    "ids_known": [123, 124, ...],
    "last_run": "2026-05-14T18:30:12+00:00",
    "snapshots_history": [
      {"date": "2026-05-14", "count": 513, "file": "snapshot_2026-05-14.json"},
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
