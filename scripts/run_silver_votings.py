"""Run the votings silver transformation and load to Supabase.

Processes only delta files not yet loaded into silver (append-only).

Usage:
    python scripts/run_silver_votings.py
    python scripts/run_silver_votings.py --dry-run
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
from bussola.silver.votings import transform

log = get_logger("bussola.silver.run_votings")

SILVER_STATE_FILE = Path("data/silver/_state.json")
SILVER_CONFIG_FILE = Path("config/silver.yaml")
ENDPOINT_KEY = "votings"


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

    parser = argparse.ArgumentParser(description="Votings silver layer loader")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    with SILVER_CONFIG_FILE.open(encoding="utf-8") as f:
        config = yaml.safe_load(f)["tables"][ENDPOINT_KEY]

    state = _load_silver_state()
    processed = set(state.get(ENDPOINT_KEY, {}).get("processed_files", []))

    bronze_dir = Path(config["bronze_dir"])
    all_files = sorted(bronze_dir.glob(config["file_pattern"]))
    new_files = [f for f in all_files if f.name not in processed]

    if not new_files:
        log.info("No new delta files to process for votings.")
        return

    log.info("Found %d unprocessed file(s): %s", len(new_files), [f.name for f in new_files])

    for file_path in new_files:
        log.info("=" * 60)
        log.info("Processing %s", file_path.name)

        records = json.loads(file_path.read_text(encoding="utf-8"))

        if not records:
            log.info("  empty delta file — skipping DB load, marking as processed.")
        else:
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

        ep = state.setdefault(ENDPOINT_KEY, {})
        ep.setdefault("processed_files", []).append(file_path.name)
        ep["last_run"] = datetime.now(timezone.utc).isoformat()
        _save_silver_state(state)

        log.info("  marked %s as processed", file_path.name)

    log.info("Votings silver complete.")


if __name__ == "__main__":
    main()
