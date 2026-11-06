# health-manager-v2 — Clean-Room Build Plan

Rebuild of the Family Health Manager (backend + frontend + desktop + packaging)
from the replication blueprint in the original repo's `docs/REPLICATION.md`.
No source is copied — contracts below are the single source of truth for both
ends until superseded.

## Contracts (pinned)

- **API**: FastAPI, all routers under `/api/v1`. Errors: FastAPI default
  `{"detail": ...}`.
- **Auth**: httpOnly cookies. `access_token` (30 min, path=/) + `refresh_token`
  (7 days, path=/api/v1/auth). Argon2 password hashes. HS256 JWTs with `jti`.
  Refresh rotation with family revocation on replay (added in Phase 2).
  Bearer header fallback accepted.
- **Env**: `APP_ENV` (development|desktop|production), `SECRET_KEY`,
  `ENCRYPTION_KEY` (dev: derived from SECRET_KEY), `DATABASE_URL`
  (sqlite+aiosqlite), `CORS_ORIGINS`, `ALLOW_REGISTRATION` (dev true).
  Production hard-requires SECRET_KEY + ENCRYPTION_KEY. Audit-agent
  fact-checking adds `WEB_FACTCHECK_ENABLED` (default false), `SEARXNG_URL`,
  `SEARXNG_TIMEOUT`, `WEB_FACTCHECK_MAX_CLAIMS`, `WEB_FACTCHECK_MAX_RESULTS`,
  and `AUDIT_MAX_CLAIMS`.
- **AI audit**: reports, health Q&A and member-scoped chat persist a
  `verifications` row whose `GET /api/v1/verifications/{id}` response gains
  an `audit` object (claim table, gaps, interactions, optional web sources).
  `family_members.web_factcheck_consent` (default false) is the explicit
  per-member opt-in for SearXNG; queries are redacted in code before egress.
  The audit is advisory: it annotates, never blocks or rewrites a report.
- **DB**: async SQLAlchemy 2.0, SQLite WAL default. Alembic from Phase 2
  (Phase 1 uses metadata.create_all).
- **Frontend**: React 19 + Vite + TS strict + Tailwind v4 (CSS-first) +
  react-router v7 + SWR. API client: cookie credentials, single-flight
  refresh on 401, 30 s timeout.
- **Version source of truth**: `backend/pyproject.toml`, synced outward.

## Phases

| # | Phase | Contents | Gate |
|---|---|---|---|
| 0 | Scaffold ✅ | repo layout, dev.sh, lefthook, Makefile, .env.example, README/CLAUDE.md | `dev.sh` boots both ends |
| 1 | Foundations ✅ | config/db/encryption/security core, auth (register/login/refresh/logout/me), members CRUD, health endpoints, frontend shell + auth pages + members page, tests green | pytest + vitest + tsc clean |
| 2 | Data model ✅ | full model set (records, medications, labs, vitals, conditions, allergies, adherence), alembic baseline + migration discipline, attachments (content-addressed, Fernet at rest), records CRUD + upload | coverage ≥ 70% new code (achieved 92%) |
| 3 | Files & views ✅ | thumbnails, PDF handling, record detail UI, timeline, dedup | e2e upload flow (Playwright, passing) |
| 4 | AI ✅ | provider abstraction (Ollama first, then cloud), extraction SSE, verification, prompts | golden-doc eval harness (F1 ≥ 0.70/doc, deterministic fake provider; `--real-ai` mode) |
| 5 | Health tracking | vitals time-series + charts, labs, pillbox/adherence, PRN/taper/cycle dosing, reminders | — |
| 6 | Desktop & packaging ✅ | Tauri 2 shell + PyInstaller onedir sidecar; server .deb, systemd units, Caddyfile | both .debs build (server deb's staged venv runs; frozen sidecar serves SPA + passes auth; desktop deb embeds the sidecar resource) |
| 7 | Breadth ✅ | 2FA, share links, backup/restore + root restore pipeline, chat, web push, reports/insights (smart report + pre-consultation), RAG grounding (local FTS5 index, seeded from your own PDF), scheduler jobs (missed-dose sweep, reminder dispatch + push, token prune) | 107 backend tests; RAG + reports verified live against Ollama |

## Non-negotiables carried over

- Never pip directly; `uv` only. Never commit `.env`. Feature branches only.
- SSE only for streaming (no WebSockets). Cookie auth end-to-end.
- SQLite `foreign_keys` deliberately OFF (replicating original behaviour).
- Encryption: `ENCRYPTION_KEY` independent of `SECRET_KEY`.
- lefthook strips AI trailers; conventional commits.
