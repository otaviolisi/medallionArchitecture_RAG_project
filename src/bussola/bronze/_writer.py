"""Shared writer for the bronze layer."""

from __future__ import annotations

import json
from pathlib import Path

from bussola.logger import get_logger

log = get_logger("bussola.bronze.writer")

BRONZE_DIR = Path("data/bronze")


def write_json(endpoint: str, file_name: str, records: list[dict]) -> Path:
    """Write records to data/bronze/<endpoint>/<file_name>.json."""
    out_dir = BRONZE_DIR / endpoint
    out_dir.mkdir(parents=True, exist_ok=True)

    out_path = out_dir / f"{file_name}.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    log.info("  wrote %d records -> %s", len(records), out_path)
    return out_path
