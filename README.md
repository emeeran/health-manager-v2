# Family Health Manager v2

Clean-room rebuild of the self-hosted, privacy-first family health record
manager: AI-powered document extraction, medication tracking with a dosing
engine, vitals time-series, pediatric growth percentiles, conversational
health Q&A grounded in your own records, and a full household/role model.

**Status:** feature-complete (parity tasklist phases 0–13 done — see
`docs/TASKLIST.md`). Shipping checklist in `docs/RELEASE.md`.

## Stack

| Layer     | Technology                                     |
|-----------|------------------------------------------------|
| Backend   | Python 3.11+, FastAPI, SQLAlchemy 2, Alembic   |
| Frontend  | React 19, Vite, TypeScript strict, Tailwind v4, SWR, React Router 7, PWA |
| Database  | SQLite (dev / default) / PostgreSQL (prod)     |
| Desktop   | Tauri 2 shell + PyInstaller sidecar (.deb)     |
| AI        | Ollama-first, OpenAI-compatible cloud optional; per-household provider config |
| Packages  | uv (Python — never pip), npm (Node)            |

## Run (development)

```bash
./dev.sh          # backend :8000 + frontend :3000 (auto port-pick)
```

First time:

```bash
cp backend/.env.example backend/.env
# set SECRET_KEY: python3 -c "import secrets; print(secrets.token_urlsafe(32))"
# set ENCRYPTION_KEY: python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
cd backend && uv sync && cd ../frontend && npm ci
```

`SECRET_KEY` signs sessions; `ENCRYPTION_KEY` encrypts PHI at rest — they
are independent on purpose and both must be set. AI works without any
cloud keys when Ollama is running locally; cloud providers are optional
and per-household consent-gated (PHI never leaves the box unless the
household opts in).

### Optional

- **Drug catalog**: the Jan Aushadhi (PMBJP) product list is bundled and
  seeds on demand: `uv run python -m app.scripts.seed_jan_aushadhi`
  (refresh with a newer export: `JAN_AUSHADHI_CSV=path uv run python -m
  app.scripts.seed_jan_aushadhi path/to/products.csv`).
- **Audit fact-checking (optional)**: reports, health Q&A and chat are
  audited against the member's records by a second agent; enable external
  checks by pointing at a SearXNG instance (`WEB_FACTCHECK_ENABLED=true`,
  `SEARXNG_URL=http://127.0.0.1:8080`). Each member must opt in from their
  profile; queries are redacted in code (no names, dates, or identifiers).
  The local audit runs with no external service.
- **Rate limiting via Redis**: set `REDIS_URL=redis://…` — the in-memory
  limiter is the default and the automatic fallback if Redis is
  unreachable.
- **Voice memos**: `uv add 'faster-whisper'` in `backend/` (optional,
  local-only transcription; the UI shows an install hint without it).
- **Push notifications**: set the `WEB_PUSH_*` VAPID vars from
  `backend/.env.example`.

## Install (server / desktop)

- Server: `bash packaging/build-deb.sh` → `health-manager_<version>_all.deb`
  (installs under `/opt/health-manager`, systemd units + Caddy config
  included; see `packaging/README.md`).
- Desktop: `bash packaging/build-desktop-deb.sh` → Tauri shell + sidecar.
  With `TAURI_SIGNING_PRIVATE_KEY` set it also emits `.deb.sig` for the
  updater; `packaging/update-manifest.sh` builds the `latest.json` feed
  (endpoint via `FHM_UPDATE_MANIFEST_URL` / pubkey via `FHM_UPDATE_PUBKEY`,
  both inert when unset).

## Test & lint

```bash
make test          # backend suite + frontend suite
make coverage      # both suites with the coverage ratchets enforced
make e2e           # Playwright suite (spins up both servers)
make lint          # ruff + mypy + eslint + tsc
```

## Layout

- `backend/` — FastAPI app (`app/core`, `app/models`, `app/routers`,
  `app/schemas`, `app/services`); Alembic migrations run on every boot
- `frontend/` — React SPA (`src/lib/api-client.ts` is the only fetch
  caller) + Playwright e2e in `frontend/e2e`
- `desktop/` — Tauri 2 shell, PyInstaller onedir sidecar
- `packaging/` — .deb builds, systemd units, Caddyfile, updater manifest
- `docs/` — `TASKLIST.md` (parity tracker), `RELEASE.md`, `PLAN.md`
