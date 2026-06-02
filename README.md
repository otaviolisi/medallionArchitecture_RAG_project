# Bússola Pública — Legislative Intelligence Pipeline

> End-to-end data engineering pipeline over the Brazilian Chamber of Deputies open API,
> built on a Medallion architecture (Bronze → Silver → Gold) with an AI/RAG layer for
> thematic classification and executive summaries.

---

## The Problem

Every week in Brasília, 513 deputies vote on bills that affect taxation, AI regulation,
infrastructure, and labor reform. Every vote is recorded, every proposition catalogued,
every expense declared. The data is public, updated daily, and exposed through a free
open API.

The challenge is not access — it is structure. Legislative data arrives as paginated
JSON across multiple endpoints, without a consolidated view, consistent history, or
a format ready for analysis. Teams that need to track specific themes, monitor
proposition status changes, or measure voting patterns end up doing this manually.

**Bússola Pública** reduces the manual effort required to collect, organize, and
monitor legislative data, creating a foundation for automated classification and alerts.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│              Câmara dos Deputados Open API                        │
│          dadosabertos.camara.leg.br/api/v2                       │
└───────────┬──────────────┬───────────────┬───────────────────────┘
            │              │               │               │
       /deputados    /partidos       /votacoes      /proposicoes
            │              │               │               │
            ▼              ▼               ▼               ▼
┌──────────────────────────────────────────────────────────────────┐
│  BRONZE  ·  Raw JSON (local)  ·  Idempotent via state.json       │
│                                                                   │
│  deputies          parties         votings      propositions      │
│  snapshot_*.json   snapshot_*.json delta_*.json delta_*.json     │
│  list + fan-out    list + fan-out  HWM-based    HWM + fan-out    │
└──────────────────────────────────────────────────────────────────┘
            │
            ▼
┌──────────────────────────────────────────────────────────────────┐
│  SILVER  ·  Pandas  ·  Supabase PostgreSQL                       │
│                                                                   │
│  silver_deputies  silver_parties  silver_votings                 │
│  silver_propositions                                             │
│                                                                   │
│  SCD Type 2 (is_current)  ·  loaded_at  ·  source_file          │
└──────────────────────────────────────────────────────────────────┘
            │
            ▼
┌──────────────────────────────────────────────────────────────────┐
│  GOLD  ·  PostgreSQL Materialized Views                          │
│                                                                   │
│  gold_deputies  gold_parties  gold_votings  gold_propositions    │
│  Flattened  ·  Business-ready  ·  Parsed social networks         │
└──────────────────────────────────────────────────────────────────┘
            │
            ▼  (roadmap)
┌──────────────────────────────────────────────────────────────────┐
│  AI / RAG  ·  pgvector  ·  OpenAI API                            │
│  Thematic classification  ·  Executive summaries  ·  Embeddings  │
└──────────────────────────────────────────────────────────────────┘
```

---

## Data Sources

| Endpoint | Extraction Strategy | Notes |
|---|---|---|
| `/deputados` | Snapshot + fan-out per deputy | Full list daily; follows `uri` for detail |
| `/partidos` | Snapshot + fan-out per party | Includes active and inactive parties |
| `/votacoes` | Incremental delta (HWM on `dataHoraRegistro`) | No fan-out; list payload is complete |
| `/proposicoes` | Incremental delta (HWM on `dataApresentacao`) + fan-out | API limited to 90-day windows; auto-chunked |

---

## Tech Stack

| Concern | Technology |
|---|---|
| HTTP client | `httpx` — retry on 5xx / 429 / timeout |
| Transformation | `pandas` + `json_normalize` |
| Database | Supabase (managed PostgreSQL + pgvector) |
| DB loader | SQLAlchemy 2.0 + psycopg2 |
| State management | `_state.json` files (bronze + silver) |
| Gold layer | PostgreSQL Materialized Views |
| AI / RAG *(roadmap)* | OpenAI API + pgvector |
| Orchestration *(roadmap)* | n8n |

---

## Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv)
- A [Supabase](https://supabase.com) project (free tier works)

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
# Fill in DATABASE_URL with your Supabase connection pooler string
```

`.env`
```env
DATABASE_URL=postgresql://postgres.<ref>:<password>@<host>.pooler.supabase.com:6543/postgres
```

---

## Running the Pipeline

### Bronze — Raw Ingestion

```bash
# Deputies (~513 records + fan-out per deputy)
uv run scripts/run_deputies.py

# Parties (~21 records + fan-out per party)
uv run scripts/run_parties.py

# Votings (incremental; defaults to last 3 months on first run)
uv run scripts/run_votings.py

# Propositions (incremental; ~98k records over 12 months — long-running)
uv run scripts/run_propositions.py --limit 10  # smoke test first
uv run scripts/run_propositions.py             # full backfill
```

> Re-runs are idempotent. `data/bronze/_state.json` tracks high-water marks and
> processed snapshots so only new data is fetched.

### Silver — Transform & Load

```bash
uv run scripts/run_silver_deputies.py    # SCD Type 2 snapshot refresh
uv run scripts/run_silver_parties.py     # full overwrite
uv run scripts/run_silver_votings.py     # append new deltas
uv run scripts/run_silver_propositions.py

# Add --dry-run to inspect the DataFrame before writing to the database
uv run scripts/run_silver_deputies.py --dry-run
```

> `data/silver/_state.json` tracks which bronze files have already been loaded.
> Re-runs skip already-processed files.

### Gold — Materialized Views

Run in the Supabase SQL Editor (or any PostgreSQL client):

```sql
-- Create once
\i src/bussola/gold/gold_deputies.sql
\i src/bussola/gold/gold_parties.sql
\i src/bussola/gold/gold_votings.sql
\i src/bussola/gold/gold_propositions.sql

-- Refresh after each silver load
REFRESH MATERIALIZED VIEW gold_deputies;
REFRESH MATERIALIZED VIEW gold_parties;
REFRESH MATERIALIZED VIEW gold_votings;
REFRESH MATERIALIZED VIEW gold_propositions;
```

---

## Project Structure

```
bussola-publica/
├── config/
│   ├── settings.yaml            # API settings (base URL, timeouts, page size)
│   └── silver.yaml              # Table config per endpoint (PK, source_type, paths)
├── data/
│   ├── bronze/                  # Raw JSON snapshots and deltas (gitignored)
│   │   ├── deputies/
│   │   ├── parties/
│   │   ├── votings/
│   │   ├── propositions/
│   │   └── _state.json          # Bronze idempotency state
│   └── silver/
│       └── _state.json          # Tracks processed bronze files per endpoint
├── scripts/
│   ├── run_deputies.py          # Bronze runners
│   ├── run_parties.py
│   ├── run_votings.py
│   ├── run_propositions.py
│   ├── run_silver_deputies.py   # Silver runners
│   ├── run_silver_parties.py
│   ├── run_silver_votings.py
│   └── run_silver_propositions.py
└── src/bussola/
    ├── bronze/
    │   ├── _http.py             # httpx client with exponential-backoff retry
    │   ├── _pagination.py       # Generic paginator for Chamber API list endpoints
    │   ├── _writer.py           # JSON writer for bronze files
    │   ├── deputies.py
    │   ├── parties.py
    │   ├── votings.py
    │   └── propositions.py      # Chunked date windows + fan-out
    ├── silver/
    │   ├── _db.py               # Shared loader: SCD2 upsert / overwrite strategies
    │   ├── deputies.py
    │   ├── parties.py
    │   ├── votings.py
    │   └── propositions.py
    ├── gold/
    │   ├── gold_deputies.sql    # Parses social networks into twitter/facebook/instagram
    │   ├── gold_parties.sql
    │   ├── gold_votings.sql
    │   └── gold_propositions.sql
    ├── logger.py
    ├── settings.py
    └── state.py
```

---

## Key Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Bronze storage | Local JSON | No infra dependency at ingestion; portable |
| Idempotency | `state.json` with HWM / snapshot history | Safe re-runs without duplicates |
| Concurrency | Sequential with `sleep()` between fan-out calls | Respectful of public API rate limits |
| Silver load strategy | SCD Type 2 (`is_current`) for incremental; overwrite for full snapshots | Tracks record changes over time without duplicating data unnecessarily |
| Gold layer | PostgreSQL Materialized Views | Precomputed, query-friendly serving layer refreshed after Silver loads |
| Database | Supabase (PostgreSQL + pgvector) | Managed Postgres with native vector support for the AI layer |

---

## Roadmap

- [ ] **AI / RAG Layer** — Thematic classification of propositions using OpenAI embeddings stored in pgvector; executive summaries via GPT-4o
- [ ] **n8n Workflow** — Daily pipeline automation and Telegram / email alerts for high-priority propositions
- [ ] **Propositions full backfill** — ~98k records across 12 months
- [ ] **Production migration** — PySpark + Delta Lake + Airflow on Databricks

---

*Built by Otávio — Data Engineering portfolio project.*
