# Bússola Pública — Legislative Intelligence Pipeline

> An end-to-end data engineering portfolio project that ingests, transforms, and enriches
> data from the Brazilian Chamber of Deputies open API using a Medallion architecture
> (Bronze → Silver → Gold → AI), with thematic classification and executive summaries
> powered by OpenAI.

---

## Overview

Every week in Brasília, 513 deputies vote on bills that shape taxation, public health,
infrastructure, and labor law. Every vote is recorded, every proposition catalogued —
published through a free, public API updated daily.

The challenge is not access. It is structure.

Legislative data arrives as paginated JSON across multiple endpoints, with no consolidated
history, no consistent schema, and no format ready for analysis. Tracking thematic trends,
monitoring proposition status changes, or understanding voting patterns requires assembling
dozens of API calls manually.

**Bússola Pública** solves this with a production-grade pipeline that collects raw data,
applies SCD Type 2 history tracking, serves a clean analytical layer via materialized views,
and enriches propositions with AI-generated topic classification and executive summaries —
all with idempotent, resumable runs.

---

## Architecture

```
╔══════════════════════════════════════════════════════════════════════════╗
║               Câmara dos Deputados Open API                              ║
║           dadosabertos.camara.leg.br/api/v2                              ║
╚═══════════╦══════════════╦═══════════════╦══════════════════════════════╝
            ║              ║               ║               ║
       /deputados     /partidos       /votacoes      /proposicoes
            ║              ║               ║               ║
            ▼              ▼               ▼               ▼
╔══════════════════════════════════════════════════════════════════════════╗
║  BRONZE — Raw Ingestion                                                  ║
║  Local JSON · Idempotent via _state.json                                 ║
║                                                                          ║
║  snapshot_*.json          snapshot_*.json                                ║
║  list + fan-out           list + fan-out                                 ║
║  (deputies, parties)                                                     ║
║                                                                          ║
║  delta_*.json             delta_*.json                                   ║
║  HWM on dataHoraRegistro  HWM on dataApresentacao + fan-out             ║
║  (votings)                90-day chunked windows (propositions)          ║
╚══════════════════════════════════════════════════════════════════════════╝
            ║
            ▼  pandas · SQLAlchemy · psycopg2
╔══════════════════════════════════════════════════════════════════════════╗
║  SILVER — Typed & Historized                                             ║
║  Supabase PostgreSQL · SCD Type 2                                        ║
║                                                                          ║
║  silver_deputies      silver_parties     silver_votings                  ║
║  silver_propositions                                                     ║
║                                                                          ║
║  is_current · loaded_at · source_file                                    ║
║  strategy: snapshot | delta | overwrite (per endpoint)                   ║
╚══════════════════════════════════════════════════════════════════════════╝
            ║
            ▼  PostgreSQL Materialized Views
╔══════════════════════════════════════════════════════════════════════════╗
║  GOLD — Analytical Layer                                                 ║
║  Flattened · Business-ready · is_current = true only                     ║
║                                                                          ║
║  gold_deputies     gold_parties                                          ║
║  gold_votings      gold_propositions                                     ║
║                                                                          ║
║  Parsed social networks (twitter / facebook / instagram)                 ║
╚══════════════════════════════════════════════════════════════════════════╝
            ║
            ▼  OpenAI API
╔══════════════════════════════════════════════════════════════════════════╗
║  AI LAYER — Enrichment                                                   ║
║                                                                          ║
║  Path A · Embeddings (text-embedding-3-small)                            ║
║    Cosine similarity against 10 topic descriptions (Portuguese)          ║
║    → tema_classificado · tema_score                                      ║
║                                                                          ║
║  Path B · LLM Summaries (gpt-4o-mini)                                   ║
║    3-line executive summary per proposition                              ║
║    → resumo_executivo                                                    ║
║                                                                          ║
║  SCD2-aware: inherits AI data from history when ementa is unchanged      ║
╚══════════════════════════════════════════════════════════════════════════╝
            ║
            ▼  FastAPI · OpenAI API
╔══════════════════════════════════════════════════════════════════════════╗
║  API LAYER — Natural Language Interface                                  ║
║                                                                          ║
║  POST /ask  { "question": "..." }                                        ║
║    1. LLM generates SQL from Gold schema + question                      ║
║    2. Safety check — SELECT-only, blocks all DDL/DML                     ║
║    3. Executes against PostgreSQL                                        ║
║    4. LLM formulates a Portuguese answer from the result                 ║
║    → { question, sql, result, answer }                                   ║
║                                                                          ║
║  Auth: X-API-Key header · Swagger UI at /docs                            ║
╚══════════════════════════════════════════════════════════════════════════╝
```

---

## Data Sources

| Endpoint | Strategy | Detail |
|---|---|---|
| `/deputados` | Snapshot + fan-out | Full list snapshot per run; follows each deputy's `uri` for full profile |
| `/partidos` | Snapshot + fan-out + overwrite | Always replaces the full parties table; no history needed |
| `/votacoes` | Incremental delta (HWM) | Uses `dataHoraRegistro` as high-water mark; list payload is complete |
| `/proposicoes` | Incremental delta (HWM) + fan-out | `dataApresentacao` HWM; API limited to 90-day windows, auto-chunked |

---

## Tech Stack

| Concern | Technology |
|---|---|
| Language | Python 3.11 · `uv` package manager |
| HTTP client | `httpx` with exponential-backoff retry (5xx / 429 / timeout) |
| Transformation | `pandas` · `json_normalize` |
| Database | Supabase — managed PostgreSQL |
| DB loader | SQLAlchemy 2.0 + psycopg2 |
| State management | `_state.json` files (HWM, snapshot history, processed files) |
| Gold layer | PostgreSQL Materialized Views |
| AI — embeddings | OpenAI `text-embedding-3-small` · `numpy` cosine similarity |
| AI — summaries | OpenAI `gpt-4o-mini` · Portuguese system prompt |
| API | FastAPI · Uvicorn · Pydantic v2 |
| API auth | `X-API-Key` header validation |
| Text-to-SQL | OpenAI `gpt-4o-mini` with typed Gold schema as context |

---

## Key Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Bronze storage | Local JSON files | Zero infra dependency at ingestion; portable across environments |
| Idempotency | `_state.json` with HWM / processed file tracking | Safe to re-run at any time without creating duplicates |
| Fan-out concurrency | Sequential with `time.sleep()` | Respectful of the public API's rate limits |
| Proposition chunking | 90-day windows via `_date_chunks()` | API enforces a maximum date range per request |
| Silver history | SCD Type 2 (`is_current`) for delta endpoints | Tracks record changes over time; enables point-in-time queries |
| Silver overwrite | Full `TRUNCATE + INSERT` for parties | No meaningful history on party metadata; simpler and faster |
| Gold layer | Materialized views over `is_current = true` | Precomputed, query-friendly serving layer; refreshed after each silver load |
| AI efficiency | Inherit AI data from history when `ementa` is unchanged | Avoids redundant API calls for propositions that only had a status update |
| AI persistence | Commit to DB after each batch (embeddings) / each row (summaries) | Progress is preserved on failure; safe to resume mid-run |
| Text-to-SQL approach | Gold schema + typed columns fed as LLM context | Leverages structured data directly; no vector index needed for factual queries |
| SQL safety check | Regex + `startswith("SELECT")` before execution | Prevents any DDL/DML from reaching the database regardless of LLM output |
| Schema documentation | Column types + join rules explicitly stated in prompt | Prevents the LLM from hallucinating incompatible JOINs or non-existent relationships |

---

## Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv)
- A [Supabase](https://supabase.com) project (free tier works)
- An [OpenAI](https://platform.openai.com) API key (AI layer + API)

---

## Setup

```bash
# 1. Clone
git clone https://github.com/<your-username>/bussola-publica.git
cd bussola-publica

# 2. Install dependencies
uv sync

# 3. Configure environment
cp .env.example .env
```

`.env`
```env
# Supabase connection pooler (port 6543)
DATABASE_URL=postgresql://postgres.<ref>:<password>@<host>.pooler.supabase.com:6543/postgres

# OpenAI — required for the AI layer and the API
OPENAI_API_KEY=sk-...

# API authentication key
API_KEY=your-secret-key
```

---

## Running the Pipeline

### Bronze — Raw Ingestion

```bash
# Deputies (~513 records + fan-out)
uv run scripts/run_deputies.py

# Parties (~21 records + fan-out)
uv run scripts/run_parties.py

# Votings — incremental from last run (defaults to 3 months on first run)
uv run scripts/run_votings.py

# Propositions — incremental, 90-day chunked, fan-out per record
uv run scripts/run_propositions.py --limit 10  # smoke test first
uv run scripts/run_propositions.py             # full backfill (~98k records)
```

> Re-runs are idempotent. `data/bronze/_state.json` tracks high-water marks and
> processed snapshots — only new data is ever fetched.

---

### Silver — Transform & Load

```bash
uv run scripts/run_silver_deputies.py     # SCD Type 2 snapshot strategy
uv run scripts/run_silver_parties.py      # full overwrite
uv run scripts/run_silver_votings.py      # append new deltas
uv run scripts/run_silver_propositions.py # append new deltas

# Inspect the DataFrame before writing
uv run scripts/run_silver_deputies.py --dry-run
```

> `data/silver/_state.json` tracks which bronze files have already been loaded.
> Re-runs skip already-processed files automatically.

---

### Gold — Materialized Views

Run once in the Supabase SQL Editor (or any PostgreSQL client):

```sql
\i src/bussola/gold/gold_deputies.sql
\i src/bussola/gold/gold_parties.sql
\i src/bussola/gold/gold_votings.sql
\i src/bussola/gold/gold_propositions.sql
```

Refresh after each silver load:

```sql
REFRESH MATERIALIZED VIEW gold_deputies;
REFRESH MATERIALIZED VIEW gold_parties;
REFRESH MATERIALIZED VIEW gold_votings;
REFRESH MATERIALIZED VIEW gold_propositions;
```

---

### AI Layer — Enrichment

```bash
# Path A: classify propositions by topic via embeddings
uv run scripts/run_ai_embeddings.py

# Path B: generate executive summaries via LLM
uv run scripts/run_ai_summarizer.py
```

Both scripts are resumable. On each run they:
1. Copy AI data from historical rows where the `ementa` is unchanged (free — no API call)
2. Call the OpenAI API only for genuinely new or updated propositions
3. Persist results incrementally — safe to interrupt and re-run

---

### API — Natural Language Interface

```bash
# Install dependencies (first time only)
uv add fastapi uvicorn

# Start the API
uv run uvicorn bussola.api.main:app --reload
```

Swagger UI available at `http://localhost:8000/docs`.

**Example request:**

```bash
curl -X POST http://localhost:8000/ask \
  -H "X-API-Key: your-secret-key" \
  -H "Content-Type: application/json" \
  -d '{"question": "Quais proposições de saúde foram apresentadas em 2025?"}'
```

**Example response:**

```json
{
  "question": "Quais proposições de saúde foram apresentadas em 2025?",
  "sql": "SELECT id, ementa, \"dataApresentacao\", \"statusDescricaoSituacao\" FROM gold_propositions WHERE tema_classificado = 'Saúde' AND ano = 2025 LIMIT 50",
  "result": [ { "id": 123, "ementa": "...", ... } ],
  "answer": "Em 2025 foram apresentadas 47 proposições classificadas como Saúde. Entre elas destacam-se..."
}
```

> The `sql` field is always returned so you can inspect exactly what was executed.
> Any query that is not a pure `SELECT` is blocked before reaching the database.

---

## Project Structure

```
bussola-publica/
├── config/
│   ├── settings.yaml                 # API base URL, timeouts, page size, retry policy
│   └── silver.yaml                   # Table config per endpoint (pk, source_type, paths)
├── data/
│   ├── bronze/                       # Raw JSON files — gitignored
│   │   ├── deputies/  snapshot_*.json
│   │   ├── parties/   snapshot_*.json
│   │   ├── votings/   delta_*.json
│   │   ├── propositions/ delta_*.json
│   │   └── _state.json               # HWM + snapshot history
│   └── silver/
│       └── _state.json               # Processed bronze files per endpoint
├── scripts/
│   ├── run_deputies.py               # Bronze runners
│   ├── run_parties.py
│   ├── run_votings.py
│   ├── run_propositions.py
│   ├── run_silver_deputies.py        # Silver runners
│   ├── run_silver_parties.py
│   ├── run_silver_votings.py
│   ├── run_silver_propositions.py
│   ├── run_ai_embeddings.py          # AI runners
│   └── run_ai_summarizer.py
└── src/bussola/
    ├── bronze/
    │   ├── _http.py                  # httpx client with exponential-backoff retry
    │   ├── _pagination.py            # Generic paginator for list endpoints
    │   ├── _writer.py                # JSON writer (bronze files)
    │   ├── deputies.py               # Snapshot + fan-out
    │   ├── parties.py                # Snapshot + fan-out
    │   ├── votings.py                # Incremental delta (HWM)
    │   └── propositions.py           # Incremental delta + fan-out + 90-day chunking
    ├── silver/
    │   ├── _db.py                    # Shared loader: snapshot / delta / overwrite strategies
    │   ├── deputies.py               # transform() → DataFrame
    │   ├── parties.py
    │   ├── votings.py
    │   └── propositions.py
    ├── gold/
    │   ├── gold_deputies.sql         # Parses redeSocial JSON → twitter/facebook/instagram
    │   ├── gold_parties.sql
    │   ├── gold_votings.sql
    │   └── gold_propositions.sql
    ├── AI/
    │   ├── embeddings.py             # Path A: topic classification via cosine similarity
    │   └── summarizer.py             # Path B: 3-line summaries via gpt-4o-mini
    ├── api/
    │   ├── main.py                   # FastAPI app — POST /ask, GET /health
    │   ├── auth.py                   # X-API-Key header validation
    │   ├── schema.py                 # Pydantic request/response models
    │   └── sql_agent.py              # Text-to-SQL: schema context, safety check, execution
    ├── logger.py
    ├── settings.py
    └── state.py
```

---

## Roadmap

- [x] Bronze layer — all 4 endpoints (snapshot, delta, fan-out, 90-day chunking)
- [x] Silver layer — SCD Type 2 with three load strategies
- [x] Gold layer — PostgreSQL materialized views
- [x] AI layer — embeddings classification + LLM executive summaries
- [x] API layer — FastAPI Text-to-SQL with safety check and natural language answers
- [ ] **pgvector** — store proposition embeddings for semantic search / hybrid RAG
- [ ] **n8n orchestration** — daily pipeline automation and Telegram alerts
- [ ] **Production migration** — PySpark + Delta Lake + Airflow on Databricks

---

*Built by Otávio — Data Engineering portfolio project.*
