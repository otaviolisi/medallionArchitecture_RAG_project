"""AI Path B — executive summaries via OpenAI GPT.

Strategy:
- For each unprocessed current proposition, call gpt-4o-mini with a Portuguese
  system prompt requesting a 3-line executive summary.
- Write resumo_executivo back to silver_propositions.

Efficiency note (SCD2):
- Only processes is_current = true rows with resumo_executivo IS NULL.
- Before calling the API, _inherit_from_history() copies the summary from the
  most recent historical row where ementa is unchanged — avoids re-paying for
  propositions whose content didn't change, only whose status did.
"""

from __future__ import annotations

import os
import logging
import time

from dotenv import load_dotenv
from openai import OpenAI
from sqlalchemy import create_engine, text

load_dotenv()
log = logging.getLogger("bussola.ai.summarizer")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

SUMMARY_MODEL = "gpt-4o-mini"

SYSTEM_PROMPT = (
    "Você é um assistente especializado em legislação brasileira. "
    "Dado o texto de uma proposição legislativa, produza um resumo executivo "
    "em exatamente 3 linhas, em português, de forma clara e objetiva. "
    "Não use bullet points. Não repita o título. Foque nos impactos práticos."
)


# ---------------------------------------------------------------------------
# Schema migration
# ---------------------------------------------------------------------------

def _ensure_column(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE silver_propositions "
            "ADD COLUMN IF NOT EXISTS resumo_executivo TEXT"
        ))


# ---------------------------------------------------------------------------
# SCD2 efficiency: inherit AI data when ementa is unchanged
# ---------------------------------------------------------------------------

def _inherit_from_history(engine) -> int:
    """Copy resumo_executivo from most recent historical row when ementa is unchanged.

    Returns number of rows updated (avoids redundant API calls for status-only updates).
    """
    sql = text("""
        UPDATE silver_propositions current_row
        SET resumo_executivo = hist.resumo_executivo
        FROM (
            SELECT DISTINCT ON (id)
                id,
                ementa,
                resumo_executivo
            FROM silver_propositions
            WHERE is_current = false
              AND resumo_executivo IS NOT NULL
            ORDER BY id, loaded_at DESC
        ) hist
        WHERE current_row.is_current = true
          AND current_row.resumo_executivo IS NULL
          AND current_row.id = hist.id
          AND current_row.ementa = hist.ementa
    """)
    with engine.begin() as conn:
        result = conn.execute(sql)
        return result.rowcount


# ---------------------------------------------------------------------------
# Summary helper
# ---------------------------------------------------------------------------

def _summarize(client: OpenAI, ementa: str, ementa_detalhada: str | None) -> str:
    content = ementa_detalhada if ementa_detalhada else ementa
    response = client.chat.completions.create(
        model=SUMMARY_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        temperature=0.3,
        max_tokens=300,
    )
    return response.choices[0].message.content.strip()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def summarize_propositions() -> None:
    database_url = os.environ["DATABASE_URL"]
    engine = create_engine(database_url)
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    _ensure_column(engine)

    inherited = _inherit_from_history(engine)
    log.info("Inherited summaries for %d propositions (ementa unchanged).", inherited)

    with engine.connect() as conn:
        rows = conn.execute(text(
            'SELECT id, ementa, "ementaDetalhada" FROM silver_propositions '
            "WHERE is_current = true "
            "  AND resumo_executivo IS NULL"
        )).fetchall()

    if not rows:
        log.info("No propositions to summarize.")
        return

    log.info("%d propositions to summarize via API.", len(rows))

    for idx, (row_id, ementa, ementa_detalhada) in enumerate(rows, start=1):
        log.info("[%d/%d] Summarizing proposition id=%s...", idx, len(rows), row_id)
        try:
            summary = _summarize(client, ementa or "", ementa_detalhada)
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "UPDATE silver_propositions "
                        "SET resumo_executivo = :resumo "
                        "WHERE id = :row_id AND is_current = true"
                    ),
                    {"resumo": summary, "row_id": row_id},
                )
            time.sleep(0.3)
        except Exception as exc:
            log.warning("Failed for id=%s: %s. Skipping.", row_id, exc)
            time.sleep(2)

    log.info("Summarization complete.")


if __name__ == "__main__":
    summarize_propositions()
