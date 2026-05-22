"""Run the deputies silver transformation and load to Supabase.

Usage:
    python scripts/run_silver_deputies.py          # process all unread bronze files
    python scripts/run_silver_deputies.py --dry-run  # transform only, skip DB load
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from bussola.logger import get_logger
from bussola.silver._db import load_to_silver
from bussola.silver.deputies import transform

log = get_logger("bussola.silver.run_deputies")

SILVER_STATE_FILE = Path("data/silver/_state.json")
SILVER_CONFIG_FILE = Path("config/silver.yaml")
ENDPOINT_KEY = "deputies"


def _load_silver_state() -> dict:
    if not SILVER_STATE_FILE.exists():
        return {}
    with SILVER_STATE_FILE.open(encoding="utf-8") as f:
        return json.load(f)


def _save_silver_state(state: dict) -> None:
    SILVER_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = SILVER_STATE_FILE.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    tmp.replace(SILVER_STATE_FILE)


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Deputies silver layer loader")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Transform only — skip the DB load (useful for inspecting df_final).",
    )
    args = parser.parse_args()

    with SILVER_CONFIG_FILE.open(encoding="utf-8") as f:
        config = yaml.safe_load(f)["tables"][ENDPOINT_KEY]

    state = _load_silver_state()
    processed = set(state.get(ENDPOINT_KEY, {}).get("processed_files", []))

    bronze_dir = Path(config["bronze_dir"])
    all_files = sorted(bronze_dir.glob(config["file_pattern"]))
    new_files = [f for f in all_files if f.name not in processed]

    if not new_files:
        log.info("No new bronze files to process for deputies.")
        return

    log.info("Found %d unprocessed file(s): %s", len(new_files), [f.name for f in new_files])

    for file_path in new_files:
        log.info("=" * 60)
        log.info("Processing %s", file_path.name)

        records = json.loads(file_path.read_text(encoding="utf-8"))
        df_final = transform(records)

        log.info("  transformed %d rows", len(df_final))

        if args.dry_run:
            log.info("  --dry-run: skipping DB load. Sample:")
            print(df_final.head(3).to_string())
        else:
            load_to_silver(
                df=df_final,
                table=config["table_name"],
                pk=config["pk"],
                source_type=config["source_type"],
                source_file=file_path.name,
            )

        # Mark file as processed (even on dry-run, so re-runs stay clean)
        ep = state.setdefault(ENDPOINT_KEY, {})
        ep.setdefault("processed_files", []).append(file_path.name)
        ep["last_run"] = datetime.now(timezone.utc).isoformat()
        _save_silver_state(state)

        log.info("  marked %s as processed", file_path.name)

    log.info("Deputies silver complete.")


if __name__ == "__main__":
    main()
