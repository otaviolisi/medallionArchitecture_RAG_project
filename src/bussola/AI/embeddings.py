"""AI Path A — topic classification via OpenAI embeddings.

Strategy:
- Embed each proposition's ementa using text-embedding-3-small.
- Compute cosine similarity against 10 predefined topic descriptions (Portuguese).
- Write tema_classificado + tema_score back to silver_propositions.

Efficiency note (SCD2):
- Only processes is_current = true rows with tema_classificado IS NULL.
- Before calling the API, _inherit_from_history() copies classification from the
  most recent historical row where ementa is unchanged — avoids re-paying for
  propositions whose content didn't change, only whose status did.
"""

from __future__ import annotations

import os
import logging

import numpy as np
from dotenv import load_dotenv
from openai import OpenAI
from sqlalchemy import create_engine, text

load_dotenv()
log = logging.getLogger("bussola.ai.embeddings")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

EMBEDDING_MODEL = "text-embedding-3-small"
BATCH_SIZE = 100

TOPICS: dict[str, str] = {
    "Tributário": (
        "Impostos, taxas, contribuições, reforma tributária, isenções fiscais, "
        "Imposto de Renda, ICMS, IPI, PIS, COFINS, simples nacional."
    ),
    "Saúde": (
        "SUS, hospitais, medicamentos, planos de saúde, vigilância sanitária, "
        "doenças, vacinas, saúde mental, profissionais de saúde."
    ),
    "Educação": (
        "Escolas, universidades, ensino básico, ensino superior, MEC, professores, "
        "bolsas de estudo, ENEM, alfabetização, FUNDEB."
    ),
    "Segurança Pública": (
        "Polícia, crime, violência, presídios, drogas, armas, tráfico, "
        "lei penal, código penal, segurança nas cidades."
    ),
    "Meio Ambiente": (
        "Desmatamento, clima, sustentabilidade, poluição, reciclagem, "
        "Amazônia, unidades de conservação, agrotóxicos, biodiversidade."
    ),
    "Economia e Trabalho": (
        "Emprego, desemprego, salário mínimo, CLT, previdência social, FGTS, "
        "sindicatos, reforma trabalhista, microempresas, desenvolvimento econômico."
    ),
    "Infraestrutura e Transporte": (
        "Rodovias, ferrovias, portos, aeroportos, mobilidade urbana, saneamento, "
        "energia elétrica, habitação, obras públicas."
    ),
    "Direitos Humanos e Minorias": (
        "Igualdade racial, gênero, LGBTQi+, pessoas com deficiência, indígenas, "
        "quilombolas, direitos da criança, idosos, refugiados."
    ),
    "Administração Pública": (
        "Funcionalismo público, concursos, licitações, transparência, controle, "
        "TCU, CGU, reforma administrativa, servidores federais."
    ),
    "Agropecuária": (
        "Agricultura familiar, agronegócio, crédito rural, reforma agrária, "
        "defensivos, irrigação, pecuária, FUNRURAL, produção de alimentos."
    ),
}

# ---------------------------------------------------------------------------
# Schema migration
# ---------------------------------------------------------------------------

def _ensure_columns(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE silver_propositions "
            "ADD COLUMN IF NOT EXISTS tema_classificado TEXT"
        ))
        conn.execute(text(
            "ALTER TABLE silver_propositions "
            "ADD COLUMN IF NOT EXISTS tema_score FLOAT"
        ))

# ---------------------------------------------------------------------------
# SCD2 efficiency: inherit AI data when ementa is unchanged
# ---------------------------------------------------------------------------

def _inherit_from_history(engine) -> int:
    """Copy classification from most recent historical row when ementa is unchanged.

    Returns number of rows updated (avoids redundant API calls for status-only updates).
    """
    sql = text("""
        UPDATE silver_propositions current_row
        SET
            tema_classificado = hist.tema_classificado,
            tema_score        = hist.tema_score
        FROM (
            SELECT DISTINCT ON (id)
                id,
                ementa,
                tema_classificado,
                tema_score
            FROM silver_propositions
            WHERE is_current = false
              AND tema_classificado IS NOT NULL
            ORDER BY id, loaded_at DESC
        ) hist
        WHERE current_row.is_current = true
          AND current_row.tema_classificado IS NULL
          AND current_row.id = hist.id
          AND current_row.ementa = hist.ementa
    """)
    with engine.begin() as conn:
        result = conn.execute(sql)
        return result.rowcount

# ---------------------------------------------------------------------------
# Embedding helpers
# ---------------------------------------------------------------------------

def _embed_batch(client: OpenAI, texts: list[str]) -> np.ndarray:
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
    return np.array([item.embedding for item in response.data], dtype=np.float32)

def _cosine_similarity_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Row-wise cosine similarity: a (n, d) vs b (m, d) → (n, m)."""
    a_norm = a / (np.linalg.norm(a, axis=1, keepdims=True) + 1e-10)
    b_norm = b / (np.linalg.norm(b, axis=1, keepdims=True) + 1e-10)
    return a_norm @ b_norm.T

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def classify_propositions() -> None:
    database_url = os.environ["DATABASE_URL"]
    engine = create_engine(database_url)
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    _ensure_columns(engine)

    inherited = _inherit_from_history(engine)
    log.info("Inherited classification for %d propositions (ementa unchanged).", inherited)

    # Load rows still needing classification after inheritance
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT id, ementa FROM silver_propositions "
            "WHERE is_current = true "
            "  AND tema_classificado IS NULL "
            "  AND ementa IS NOT NULL "
            "  AND ementa != ''"
        )).fetchall()

    if not rows:
        log.info("No propositions to classify.")
        return

    log.info("%d propositions to classify via API.", len(rows))

    topic_names = list(TOPICS.keys())
    topic_descriptions = list(TOPICS.values())
    topic_embeddings = _embed_batch(client, topic_descriptions)

    total_updated = 0
    for batch_start in range(0, len(rows), BATCH_SIZE):
        batch = rows[batch_start : batch_start + BATCH_SIZE]
        ids = [r[0] for r in batch]
        ementas = [r[1] for r in batch]

        log.info(
            "Embedding batch %d-%d of %d...",
            batch_start + 1, batch_start + len(batch), len(rows),
        )
        ementa_embeddings = _embed_batch(client, ementas)
        similarities = _cosine_similarity_matrix(ementa_embeddings, topic_embeddings)

        batch_updates = []
        for i, row_id in enumerate(ids):
            best_idx = int(np.argmax(similarities[i]))
            batch_updates.append({
                "row_id": row_id,
                "tema": topic_names[best_idx],
                "score": float(similarities[i, best_idx]),
            })

        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE silver_propositions "
                    "SET tema_classificado = :tema, tema_score = :score "
                    "WHERE id = :row_id AND is_current = true"
                ),
                batch_updates,
            )
        total_updated += len(batch_updates)
        log.info("Saved batch. Total updated so far: %d.", total_updated)

    log.info("Classification complete. %d rows updated.", total_updated)

if __name__ == "__main__":
    classify_propositions()
