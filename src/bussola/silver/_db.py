"""Shared DB loader for the silver layer.

Handles:
- Postgres connection via DATABASE_URL
- CREATE TABLE IF NOT EXISTS (schema inferred from DataFrame)
- SCD Type 2 upsert:
    snapshot → expire ALL is_current rows, insert new batch
    delta    → expire only rows whose PK is in the new batch
- Adds is_current, loaded_at, source_file metadata columns automatically
"""

from __future__ import annotations

import json as json_lib
import os
from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import create_engine, text

from bussola.logger import get_logger

log = get_logger("bussola.silver.db")

SILVER_CONFIG_PATH = "config/silver.yaml"


def _get_engine():
    return create_engine(os.environ["DATABASE_URL"])


def _serialize_complex_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Serialize list/dict columns to JSON strings for Postgres compatibility."""
    df = df.copy()
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].apply(
                lambda x: json_lib.dumps(x, ensure_ascii=False)
                if isinstance(x, (list, dict)) else x
            )
    return df


def _table_exists(engine, table: str) -> bool:
    with engine.connect() as conn:
        result = conn.execute(
            text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = :table
                )
            """),
            {"table": table},
        )
        return result.scalar()


def load_to_silver(
    df: pd.DataFrame,
    table: str,
    pk: str,
    source_type: str,
    source_file: str,
) -> int:
    """Load a transformed DataFrame into the silver Postgres table.

    Args:
        df: output of a silver transform function (clean, typed columns).
        table: target Postgres table name.
        pk: primary key column name.
        source_type: "snapshot" or "delta" — controls expiry strategy.
        source_file: bronze filename being processed (audit trail).

    Returns:
        Number of rows inserted.
    """
    df = _serialize_complex_columns(df)
    df["is_current"] = True
    df["loaded_at"] = datetime.now(timezone.utc)
    df["source_file"] = source_file

    engine = _get_engine()
    exists = _table_exists(engine, table)

    with engine.begin() as conn:
        if exists:
            if source_type == "snapshot":
                conn.execute(
                    text(f'UPDATE "{table}" SET is_current = false WHERE is_current = true')
                )
                log.info("  expired all current rows in %s (snapshot refresh)", table)
            else:
                pk_values = df[pk].tolist()
                conn.execute(
                    text(
                        f'UPDATE "{table}" SET is_current = false'
                        f" WHERE {pk} = ANY(:pks) AND is_current = true"
                    ),
                    {"pks": pk_values},
                )
                log.info("  expired rows for %d PKs in %s (delta)", len(pk_values), table)

        df.to_sql(table, con=conn, if_exists="append", index=False)

    log.info("  inserted %d rows into %s", len(df), table)
    return len(df)
