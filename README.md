# Bussola Publica

Legislative intelligence pipeline that ingests open data from the Brazilian
Chamber of Deputies API, processes it through a medallion architecture
(bronze / silver / gold), and enriches it with AI.

> Status: 🚧 Phase 1 — Bronze layer — `deputies` endpoint

## Why this project

Every Wednesday, 513 deputies in Brasilia vote on legislation that directly
affects taxes, regulation, labor rules, and AI policy. All of this is public
data, refreshed daily, available through an open API. Yet most companies and
even the press still consume it by hand.

This project demonstrates how data engineering turns that noisy public stream
into structured, queryable, AI-enriched intelligence.

## Architecture

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Chamber   │ →  │   BRONZE    │ →  │   SILVER    │ →  │    GOLD     │
│     API     │    │  raw JSON   │    │ typed/dedup │    │ star schema │
│             │    │  snapshot   │    │  (Parquet)  │    │ + AI fields │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
```

## Current scope: `deputies` only

This iteration focuses exclusively on the `/deputados` endpoint, end to end.
Other endpoints (parties, propositions, votings) will follow the same pattern
in their own modules and runner scripts.

## Project layout

```
bussola-publica/
├── config/
│   └── settings.yaml              # shared: base URL, pagination, retries
├── data/
│   ├── bronze/
│   │   ├── _state.json            # snapshot history + idempotency state
│   │   └── deputies/
│   │       └── snapshot_<date>.json
│   ├── silver/                    # next phase
│   └── gold/                      # next phase
├── logs/
│   └── pipeline.log               # generated at runtime
├── scripts/
│   └── run_deputies.py            # CLI for deputies
└── src/bussola/
    ├── __init__.py
    ├── logger.py
    ├── settings.py
    ├── state.py
    └── bronze/
        ├── _http.py               # shared HTTP client + retry
        ├── _pagination.py         # shared paginator
        ├── _writer.py             # shared JSON writer
        └── deputies.py            # deputies extractor
```

## Architectural decisions

### One module per endpoint, one runner per endpoint

Each Chamber API endpoint will get its own module under
`src/bussola/bronze/` and its own runner script under `scripts/`.
The bronze package init is intentionally empty: no shared registry,
no imports cascading across endpoints. Adding a new endpoint means
adding two files (`bronze/<name>.py` + `scripts/run_<name>.py`)
without touching anything else.

### Bronze stores enriched records (list + detail merged)

The Chamber API uses a fan-out pattern: a list call returns a summary
plus a `uri` field pointing to the detailed record. Rather than saving
N detail files + 1 list file per snapshot, bronze saves a single JSON
where each record has the shape:

```json
{
  "id": 220714,
  "summary": { /* original payload from /deputados list call */ },
  "detail":  { /* original payload from /deputados/{id} call */ }
}
```

This is a small departure from a purist bronze ("save raw, never transform"):
two raw payloads are merged into one envelope. The trade-off is intentional —
silver consumption gets simpler, and provenance is preserved through the
`summary` / `detail` split.

### Snapshot semantics: always re-run, record history

Deputies is a **snapshot endpoint**. The "current truth" is the API as of right
now. Re-running is always valid (and desired) because deputies switch parties,
change status, enter and leave office.

Each run:
1. Writes `data/bronze/deputies/snapshot_<today>.json` (overwrites if same day).
2. Appends an entry to `snapshots_history` in `data/bronze/_state.json`.

The history list is the audit trail — never deleted, append-only.

State file shape after a few runs:

```json
{
  "deputies": {
    "last_snapshot": "2026-05-18",
    "ids_known": [66828, 73441, ..., 220714],
    "last_run": "2026-05-18T18:30:12+00:00",
    "snapshots_history": [
      {"date": "2026-05-14", "count": 513, "file": "snapshot_2026-05-14.json", "ran_at": "..."},
      {"date": "2026-05-15", "count": 513, "file": "snapshot_2026-05-15.json", "ran_at": "..."},
      {"date": "2026-05-18", "count": 514, "file": "snapshot_2026-05-18.json", "ran_at": "..."}
    ]
  }
}
```

## Setup

```bash
# 1. Create a virtual environment
uv venv

# 2. Activate it
source .venv/bin/activate           # macOS / Linux
# .venv\Scripts\activate            # Windows

# 3. Install the package in editable mode (with its dependencies)
uv pip install -e .

# 4. Copy environment template
cp .env.example .env
```

## How to run

```bash
# Smoke test: 3 deputies, full fan-out
python scripts/run_deputies.py --limit 3

# Full snapshot (~513 deputies, ~2 minutes)
python scripts/run_deputies.py
```

## Stack

| Concern          | Tool                                     |
|------------------|------------------------------------------|
| Language         | Python 3.11+                             |
| Package manager  | uv                                       |
| HTTP             | httpx                                    |
| Config           | YAML + python-dotenv                     |
| Bronze (current) | Local JSON                               |
| Silver (planned) | Pandas / PySpark → Parquet               |
| Gold (planned)   | PostgreSQL (Supabase) + pgvector         |
| AI enrichment    | OpenAI embeddings + structured summaries |
| Orchestration    | Airflow (planned)                        |

## Roadmap

- [x] **Bronze · deputies** — snapshot with fan-out
- [ ] **Bronze · parties** — same pattern
- [ ] **Bronze · propositions** — incremental by date
- [ ] **Bronze · votings** — incremental by date
- [ ] **Silver** — type enforcement, deduplication, validation → Parquet
- [ ] **Gold** — star schema in PostgreSQL with AI-enriched fields
- [ ] **AI layer** — thematic classification (embeddings) + executive summaries
- [ ] **Orchestration** — scheduled runs

## License

MIT
