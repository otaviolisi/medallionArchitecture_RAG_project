"""Text-to-SQL agent over the Gold materialized views.

Flow:
  1. Build a prompt with the Gold schema + user question.
  2. Ask the LLM to generate a read-only SQL query.
  3. Safety-check the SQL (SELECT-only, no DDL/DML).
  4. Execute against PostgreSQL.
  5. Ask the LLM to formulate a Portuguese answer from the result.
"""

from __future__ import annotations

import re
import logging
from typing import Any

from openai import OpenAI
from sqlalchemy import create_engine, text

log = logging.getLogger("bussola.api.sql_agent")

# ---------------------------------------------------------------------------
# Gold schema — fed to the LLM as context
# ---------------------------------------------------------------------------

GOLD_SCHEMA = """
You have access to the following PostgreSQL materialized views.
All column names are CASE-SENSITIVE — always wrap them in double quotes if they contain uppercase letters.

─────────────────────────────────────────────
TABLE: gold_deputies
  Description: Current federal deputies of the Brazilian Chamber of Deputies.
  Columns:
    id                   BIGINT        -- unique deputy identifier
    "nomeCivil"          TEXT          -- full legal name
    "nomeEleitoral"      TEXT          -- electoral name (commonly used)
    partido              TEXT          -- party acronym (e.g. 'PT', 'PL', 'MDB')
    estado               TEXT          -- state abbreviation (e.g. 'SP', 'RJ')
    email                TEXT
    situacao             TEXT          -- current mandate status
    "condicaoEleitoral"  TEXT
    escolaridade         TEXT
    "dataNascimento"     TEXT
    "ufNascimento"       TEXT
    "municipioNascimento" TEXT
    sexo                 TEXT          -- 'M' or 'F'
    "idLegislatura"      BIGINT
    twitter              TEXT
    facebook             TEXT
    instagram            TEXT
    loaded_at            TIMESTAMPTZ

─────────────────────────────────────────────
TABLE: gold_parties
  Description: Political parties registered in the Chamber.
  Columns:
    id                   BIGINT        -- unique party identifier
    sigla                TEXT          -- party acronym (e.g. 'PT', 'PL') — use this to join with gold_deputies.partido
    nome                 TEXT          -- full party name
    "statusData"         TEXT
    "statusIdLegislatura" BIGINT
    "statusSituacao"     TEXT
    "statusTotalPosse"   BIGINT        -- total seats held
    "statusTotalMembros" BIGINT        -- total members
    "liderNome"          TEXT          -- party leader name
    "liderSiglaPartido"  TEXT
    "liderUf"            TEXT
    "liderIdLegislatura" BIGINT
    "urlWebSite"         TEXT
    "urlFacebook"        TEXT
    loaded_at            TIMESTAMPTZ

─────────────────────────────────────────────
TABLE: gold_votings
  Description: Voting sessions held in the Chamber.
  Columns:
    id                   BIGINT        -- unique voting session identifier
    data                 DATE
    "dataHoraRegistro"   TIMESTAMPTZ
    "siglaOrgao"         TEXT          -- committee or floor (e.g. 'PLEN' = Plenário)
    "proposicaoObjeto"   TEXT          -- free-text description of the proposition voted on
    descricao            TEXT          -- voting session description
    aprovacao            INTEGER       -- 1 = approved, 0 = rejected
    loaded_at            TIMESTAMPTZ

─────────────────────────────────────────────
TABLE: gold_propositions
  Description: Legislative propositions presented at the Chamber.
  Columns:
    id                          BIGINT   -- unique proposition identifier
    "siglaTipo"                 TEXT     -- proposition type acronym (e.g. 'PL', 'PEC', 'MPV')
    "codTipo"                   BIGINT
    numero                      BIGINT   -- proposition number
    ano                         BIGINT   -- year presented
    ementa                      TEXT     -- short description of the proposition
    "dataApresentacao"          DATE
    "statusDataHora"            TIMESTAMPTZ
    "statusSequencia"           BIGINT
    "statusSiglaOrgao"          TEXT     -- current committee handling it
    "statusRegime"              TEXT
    "statusDescricaoTramitacao" TEXT
    "statusCodTipoTramitacao"   BIGINT
    "statusDescricaoSituacao"   TEXT     -- current status description
    "statusCodSituacao"         BIGINT
    "statusDespacho"            TEXT
    "statusAmbito"              TEXT
    "statusApreciacao"          TEXT
    "descricaoTipo"             TEXT
    "ementaDetalhada"           TEXT     -- extended description (may be null)
    keywords                    TEXT
    tema_classificado           TEXT     -- AI topic: 'Saúde', 'Tributário', 'Educação',
                                         --   'Segurança Pública', 'Meio Ambiente',
                                         --   'Economia e Trabalho', 'Infraestrutura e Transporte',
                                         --   'Direitos Humanos e Minorias',
                                         --   'Administração Pública', 'Agropecuária'
    tema_score                  FLOAT    -- cosine similarity score (0–1)
    resumo_executivo            TEXT     -- AI-generated 3-line executive summary
    loaded_at                   TIMESTAMPTZ

─────────────────────────────────────────────
RELATIONSHIPS AND JOIN RULES:

  gold_deputies  →  gold_parties:
    JOIN gold_parties p ON p.sigla = d.partido
    (gold_deputies.partido is a TEXT acronym matching gold_parties.sigla)

  gold_votings.proposicaoObjeto is a free-text description — it is NOT a foreign key
    and cannot be reliably joined to gold_propositions.id.

  gold_propositions does NOT contain a deputy or party column.
    There is no direct join between gold_propositions and gold_deputies or gold_parties.
    For questions about which party authored propositions, answer using only
    the data available — do not fabricate joins.

  gold_votings does NOT contain a deputy column.
    There is no direct join between gold_votings and gold_deputies.

IMPORTANT CONSTRAINTS:
  - Never JOIN tables on columns with incompatible types.
  - Never invent columns or relationships that are not listed above.
  - If a question requires a relationship that does not exist in this schema,
    answer as best you can with the available data and use a comment in the SQL
    to note the limitation.
  - For questions about political ideology (left/right/far-right), use
    tema_classificado, keywords, and ementa text search — there is no ideology column.
    Use ILIKE for text searches on ementa and keywords.
"""

SQL_SYSTEM_PROMPT = (
    "You are a SQL expert for Brazilian legislative data. "
    "Given a schema and a user question in Portuguese, generate a single "
    "read-only PostgreSQL SELECT query that answers the question. "
    "Return ONLY the raw SQL — no markdown, no explanation, no code fences. "
    "Always use double quotes for column names that contain uppercase letters. "
    "Limit results to 50 rows unless the user asks for more. "
    "Never use INSERT, UPDATE, DELETE, DROP, TRUNCATE, ALTER, or any DDL/DML."
)

ANSWER_SYSTEM_PROMPT = (
    "You are an assistant specialized in Brazilian legislative data. "
    "Given a user question, the SQL query that was executed, and the query results, "
    "write a clear, concise answer in Portuguese. "
    "Be objective. If the result is empty, say so clearly. "
    "Do not repeat the SQL. Do not use technical jargon."
)

# DDL/DML keywords that must never appear in a safe query
_BLOCKED = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|REPLACE|MERGE"
    r"|GRANT|REVOKE|EXEC|EXECUTE|CALL)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Safety check
# ---------------------------------------------------------------------------

def _check_sql_safety(sql: str) -> None:
    """Raise ValueError if the SQL contains any non-SELECT statement."""
    stripped = sql.strip().lstrip(";").strip()
    if not stripped.upper().startswith("SELECT"):
        raise ValueError(f"Query must start with SELECT. Got: {stripped[:60]!r}")
    if _BLOCKED.search(stripped):
        match = _BLOCKED.search(stripped)
        raise ValueError(f"Blocked keyword detected in SQL: {match.group()!r}")


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

def run(question: str, database_url: str, openai_api_key: str) -> dict[str, Any]:
    client = OpenAI(api_key=openai_api_key)
    engine = create_engine(database_url)

    # Step 1 — generate SQL
    sql_response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SQL_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"{GOLD_SCHEMA}\n\nQuestion: {question}",
            },
        ],
        temperature=0,
        max_tokens=500,
    )
    sql = sql_response.choices[0].message.content.strip()
    log.info("Generated SQL: %s", sql)

    # Step 2 — safety check
    _check_sql_safety(sql)

    # Step 3 — execute
    with engine.connect() as conn:
        rows = conn.execute(text(sql)).mappings().fetchall()
    result = [dict(row) for row in rows]
    log.info("Query returned %d rows.", len(result))

    # Step 4 — formulate answer
    answer_response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Question: {question}\n\n"
                    f"SQL executed:\n{sql}\n\n"
                    f"Result ({len(result)} rows):\n{result[:20]}"
                ),
            },
        ],
        temperature=0.3,
        max_tokens=600,
    )
    answer = answer_response.choices[0].message.content.strip()

    return {
        "question": question,
        "sql": sql,
        "result": result,
        "answer": answer,
    }
