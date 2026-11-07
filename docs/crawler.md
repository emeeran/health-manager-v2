# Medicine Catalog Crawler

Documentation for the 1mg.com / Apollo Pharmacy catalog crawler: the standalone
crawler, its scheduler integration, the Settings toggle, and how the crawled
catalog feeds the app's drug features.

## Architecture

```
Sitemaps (public)                    App (backend)
┌─────────────────────┐              ┌──────────────────────────────┐
│ 1mg  sitemap_drugs_*.xml │         │  Settings toggle (app_secrets)│
│ Apollo pharma-rx/otc.xml │  ───▶   │        │ on                   │
└─────────────────────┘              │        ▼                      │
        │                            │  APScheduler job              │
        ▼                            │  crawl_medicine_catalog       │
┌─────────────────────┐              │  (every 30 min, bounded)      │
│ tools/crawl.py       │  ◀──runs──  │        │                      │
│ checkpoint SQLite     │            │        ▼                      │
│ ~/…/data/crawl.db    │  ──sync──▶ │  crawler_drugs table          │
└─────────────────────┘              │        │                      │
                                     │  ┌─────┴──────────────┐       │
                                     │  │ /drugs/search       │       │
                                     │  │ /drugs/price-compare│       │
                                     │  │ /drug-info          │       │
                                     │  │ /allergy-conflicts  │       │
                                     │  │ chat grounding      │       │
                                     │  │ interaction prompts │       │
                                     │  └────────────────────┘       │
                                     └──────────────────────────────┘
```

Two cooperating pieces:

1. **Standalone crawler** — `backend/tools/crawl.py` (stdlib-only Python).
   Discovers drug URLs from both sites' public sitemaps, fetches pages
   politely, extracts factual fields into a checkpoint SQLite DB, and exports
   `medicine_full.csv`. Resumable: every URL's status persists, so it can be
   stopped/killed and relaunched.
2. **In-app integration** — a self-gating scheduler job runs bounded crawl
   batches via subprocess and syncs the results into the app's
   `crawler_drugs` table, which powers the drug endpoints and AI contexts.

## Data extracted (factual fields only)

Per drug page, one row: `source` (1mg/apollo), `url`, `brand_name`,
`generic_name`, `manufacturer`, `pack_size`, `price_mrp`, `price_selling`,
`discount_pct`, `dosage_form`, `uses`, `side_effects`, safety fields
(alcohol/pregnancy/breastfeeding/driving/liver/kidney), `habit_forming`,
`therapeutic_class`, `prescription_required`, `category_path`,
`description_brief`, `page_last_updated`.

Extraction paths: 1mg pages embed the full drug record in
`window.__INITIAL_STATE__` (parsed directly); Apollo pages expose a
schema.org `Drug` JSON-LD block plus FAQ schema. Neither site offers an open
content API — the server-rendered HTML *is* the per-page database dump. Long
editorial prose is deliberately **not** stored; only factual fields, capped
in length.

## Scale

| Source | Drug URLs | Source of URLs |
|---|---|---|
| 1mg | ~387k | `https://www.1mg.com/sitemap.xml` → 78 × `sitemap_drugs_N.xml` |
| Apollo | ~250k | `sitemap-master.xml` → `sitemap-pharma-rx.xml` + `sitemap-pharma-otc.xml` (English) |

Full-crawl ETA from one machine: days. The crawler is checkpointed, so it
runs in pieces.

## Standalone crawler usage

```bash
cd backend
uv run python tools/crawl.py discover --site all          # fetch sitemaps → URL queue
uv run python tools/crawl.py crawl --site all --limit 400 --export   # one bounded batch + CSV
uv run python tools/crawl.py refresh --days 7 --limit 1000           # re-enqueue stale pages
uv run python tools/crawl.py status                       # per-site status counts
uv run python tools/crawl.py export                       # rows → medicine_full.csv
```

- `--data DIR` (or `MEDICINE_CRAWLER_DATA_DIR` env) relocates the checkpoint
  DB / CSV / JSONL. Defaults to `backend/data/medicine-crawler/`.
- The last line of a `crawl`/`refresh` run is always `RESULT {...}` for
  callers to parse.
- Politeness: default 8 workers × 0.3s delay, gzip, retry-with-backoff on
  429/5xx, automatic 10-minute pause after a burst of 403s.

## App integration

### Settings toggle

Settings → Data → **Medicine catalog crawler** (admin only, audited).

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/system/medicine-crawler` | `{enabled, source, batch_pages, data_dir, script_present}` |
| `PUT /api/v1/system/medicine-crawler` | `{"enabled": bool}` — stored in `app_secrets`, survives restarts |
| `POST /api/v1/system/medicine-crawler/sync` | Pull crawled rows into `crawler_drugs` now (safe mid-crawl) |

`MEDICINE_CRAWLER_ENABLED` env is only the default (off); the stored toggle
beats it. Off → the scheduler tick no-ops.

### Scheduler job

`crawl_medicine_catalog` (registered in `app/core/scheduler.py`, body in
`app/core/jobs.py`):

1. Read the toggle — off → `{"status": "disabled"}`.
2. Re-enqueue pages last crawled >7 days ago (steady-state price refresh).
3. Run one batch: `tools/crawl.py crawl --site all --limit $MEDICINE_CRAWLER_BATCH_PAGES --export` (subprocess, killed at `MEDICINE_CRAWLER_TIMEOUT_SECONDS`).
4. Sync new/updated rows into `crawler_drugs`.

Knobs (env): `MEDICINE_CRAWL_BATCH_MINUTES` (30), `MEDICINE_CRAWLER_BATCH_PAGES` (400),
`MEDICINE_CRAWLER_TIMEOUT_SECONDS` (900), `MEDICINE_CRAWLER_DATA_DIR`,
`MEDICINE_CRAWLER_ENABLED`.

### Sync into the app

`app/services/crawler_drug_service.sync_from_crawler_db()` reads the crawler
SQLite (`rows` table) and upserts by URL into `crawler_drugs` — re-syncs
refresh prices in place, safe mid-crawl. Brand names are normalized with the
same function as the Jan Aushadhi catalog (`local_drug_service.normalize_drug_name`)
so both sources interoperate.

## Where the catalog is used

| Feature | Endpoint | Integration |
|---|---|---|
| Drug search | `GET /drugs/search` | Jan Aushadhi rows + crawler rows (`catalog: "1mg"/"apollo"`, `price`, `url`) |
| Price comparison | `POST /drugs/price-compare` | Each item gets `pharmacy_offers` (cheapest first, exact + partial matches) and `offers_matched_count` |
| Drug info flyout | `GET /members/{id}/drug-info` | Catalog is the **local-first source** (`source: "catalog"`) before openFDA → RxNorm → AI; adds `price`, `price_mrp`, `url` |
| Allergy conflicts | `GET /members/{id}/allergy-conflicts` | Brand → generic via catalog: a "Duloxetine" allergy flags "Duzela M 30 Capsule" (`matched_on: "catalog_generic"`) |
| Interaction checks | `POST /members/{id}/drug-interactions[/pair]` | `{drug_context}` prompt section gives the AI real generic compositions instead of brand-string guesses |
| Chat | `POST /conversations/{id}/messages/stream` | Catalog grounding block (active meds + drug-like question terms) alongside the RAG block; returned in `sources` |

Offer matching: exact normalized-name match first, then a looser token-prefix
top-up (≥ half the tokens, minimum 2) so pack variants ("Capsule DR" vs
"10's") still surface; labeled `match: "exact" | "partial"`.

## Safety notes

- **Untrusted third-party text**: crawled `uses`/`side_effects` prose enters
  AI prompts. It is length-capped at sync and every prompt block is prefixed
  with an untrusted-data warning; interaction matching stays on names, not
  free text.
- **Politeness**: bounded batches, delays, backoff, block-pause. Don't raise
  concurrency much — Apollo throttles aggressively (429s).
- **Not a purchase channel**: catalog rows are metadata for decision support,
  same stance as the Jan Aushadhi catalog.
- Toggle default is **off**; enabling it is an explicit admin action.

## Current deployment notes

- `backend/.env` (local, uncommitted):
  `MEDICINE_CRAWLER_DATA_DIR=/home/em/code/medicine-crawler/data` — the app
  shares the standalone full-crawl checkpoint DB. Do **not** move or delete
  that directory.
- A standalone full crawl (638k URLs) ran/was running in
  `~/code/medicine-crawler/`; the app gets its data from the same DB.
- `backend/data/medicine-crawler/` is the default app-side data dir when the
  env var is absent.

## Tests

- `tests/test_medicine_crawler.py` — toggle precedence, job gating, stale requeue
- `tests/test_crawler_drugs.py` — sync upsert/idempotency, search, offers
- `tests/test_crawler_integrations.py` — chat grounding, interaction prompt
  enrichment, drug-info catalog source, allergy catalog-generic matching
- Existing suites (`test_drug_info_suite`, `test_drug_interactions`,
  `test_ai_tools_reports`, `test_breadth`) prove the non-catalog paths are
  unchanged.
