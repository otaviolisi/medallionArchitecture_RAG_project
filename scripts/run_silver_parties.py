"""Run the parties silver transformation and load to Supabase.

Always processes the latest bronze snapshot and overwrites the table.

Usage:
    python scripts/run_silver_parties.py
    python scripts/run_silver_parties.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from bussola.logger import get_logger
from bussola.silver._db import load_to_silver
from bussola.silver.parties import transform

log = get_logger("bussola.silver.run_parties")

SILVER_CONFIG_FILE = Path("config/silver.yaml")
ENDPOINT_KEY = "parties"


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Parties silver layer loader")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    with SILVER_CONFIG_FILE.open(encoding="utf-8") as f:
        config = yaml.safe_load(f)["tables"][ENDPOINT_KEY]

    bronze_dir = Path(config["bronze_dir"])
    all_files = sorted(bronze_dir.glob(config["file_pattern"]))

    if not all_files:
        log.info("No snapshot files found in %s.", bronze_dir)
        return

    # Overwrite always uses the latest snapshot
    latest_file = all_files[-1]
    log.info("Processing latest snapshot: %s", latest_file.name)

    records = json.loads(latest_file.read_text(encoding="utf-8"))
    df_final = transform(records)
    log.info("Transformed %d rows.", len(df_final))

    if args.dry_run:
        log.info("--dry-run: skipping DB load. Sample:")
        print(df_final.head(3).to_string())
        return

    load_to_silver(
        df=df_final,
        table=config["table_name"],
        pk=config["pk"],
        source_type=config["source_type"],
        source_file=latest_file.name,
    )

    log.info("Parties silver complete.")


if __name__ == "__main__":
    main()
