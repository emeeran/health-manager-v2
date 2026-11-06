# health-manager-v2 — Full-Parity Task List

Derived from the original repo's `docs/REPLICATION.md` (v1.5.58). Extends
`docs/PLAN.md`: phases 0–7 are done; phases 8–14 close every remaining gap
between v2 and the blueprint. Each phase ends with an e2e gate — no phase is
"done" until its gate passes.

Legend: ✅ already built in v2 · 🔧 extension of something v2 has · ⬜ net-new.

---

## Phase 0 — Scaffold ✅
- [x] Repo layout, dev.sh, lefthook, Makefile, .env.example (REP §2, §9)

## Phase 1 — Foundations ✅
- [x] Config/db/encryption/security core; auth register/login/refresh/logout/me
- [x] Members CRUD + frontend shell, auth pages, members page

## Phase 2 — Data model ✅
- [x] records, medications, labs, vitals, conditions, allergies, adherence models
- [x] Alembic baseline + migration discipline; attachments (content-addressed, Fernet)

## Phase 3 — Files & views ✅
- [x] Thumbnails, PDF handling, record detail UI, timeline, dedup

## Phase 4 — AI ✅
- [x] Provider abstraction (Ollama-first + cloud), extraction SSE, verification, prompts
- [x] Golden-doc eval harness (deterministic fake provider, `--real-ai` mode)

## Phase 5 — Health tracking ✅
- [x] Vitals time-series + charts, labs, pillbox/adherence, PRN/taper/cycle, reminders

## Phase 6 — Desktop & packaging ✅
- [x] Tauri 2 shell + PyInstaller onedir sidecar; server .deb, systemd, Caddyfile

## Phase 7 — Breadth ✅
- [x] 2FA, share links, backup/restore + root restore pipeline, chat, web push,
      smart report + pre-consultation, FTS5 RAG grounding, scheduler jobs

---

## Phase 8 — Household administration & roles ✅ (REP §4.5, §4.6 Auth/users)

Backend:
- [x] `household_users` router: invitations, role assignment (admin/member/viewer),
      admin-only guards — `require_household_admin` dependency
- [x] Role enforcement in `deps`: viewer blocked from mutating methods except
      read-only-POST prefixes (`/smart-search`, `/smart-entry`, `/conversations`)
- [x] `household` router: household settings + per-household AI provider config
      (`households.settings_json`: ordered providers[], primary_provider
      auto|cloud|local, gemini_auth) — replaces v2's env-only provider config
- [x] `security_audit` router + audit-log writes on sensitive actions
      (logins, restores, role changes); encrypted `detail` column
- [x] `system` router: instance-admin provider keys backed by encrypted
      `app_secrets` rows (runtime credential resolver: app_secrets → env fallback,
      SSRF blocklist on Ollama URL)
- [x] `notifications` router (in-app list/read) + notifications table
- [x] `ALLOW_REGISTRATION=false` default in production; later users join via
      invitation (REP gotcha #13)

Frontend:
- [x] Household settings UI: name, members table with role edit, invite flow
- [x] Settings → AI Providers tab: per-provider enable/order/keys/model
      fetch/status (talks to household config + `/system` keys)
- [x] Notification bell + unread state in AppLayout header

Tests:
- [x] Role-matrix tests (admin/member/viewer × mutating/read endpoints)
- [x] Invitation lifecycle tests; audit-log write assertions

Gate: role matrix e2e (admin invites viewer → viewer blocked from mutation),
AI provider config survives backend restart.

## Phase 9 — People breadth ✅ (REP §4.6 People)

Backend:
- [x] `providers` router + model: doctor/facility directory (CRUD, specialty,
      hospital); `provider_assignments` (member↔provider, UHID)
- [x] `insurance` router + models: `insurance_policies`, `insurance_claims`
      (policy CRUD, claim tracking per member)
- [x] `member_emergency`: ICE card data (emergency contacts, blood group,
      allergies summary) — feeds the QR card
- [x] `member_history` router: chronological cross-domain history feed
- [x] Encrypted member fields: phone/address/history/emergency contacts
      (`EncryptedText`); records gain an optional `provider_id` link

Frontend:
- [x] `/providers` directory page (list/add/remove); provider picker in the
      record form + provider shown on record detail; UHID field on assignment
- [x] Care team + insurance sections on the member page
- [x] `/members/:id/emergency` ICE card page with printable QR (react-qr-code)

Tests: provider/insurance CRUD integration tests (incl. at-rest ciphertext
assertions via raw SQL); ICE-card Playwright smoke (provider → assign → QR).

Gate: create provider → assign to member → reference it from a record →
visible on member page and ICE card.

## Phase 10 — Health records breadth ✅ (REP §4.6 Records)

Backend (v2 has dead models for conditions/allergies — wire them up):
- [x] `conditions` router: condition episodes CRUD, status transitions
- [x] `allergies` router: CRUD + conflict detection (allergy vs prescribed drug)
- [x] `vaccinations` + `immunizations` routers: schedule + dose history
- [x] `symptoms` router: symptom entries with severity/duration
- [x] `growth` router: CDC LMS percentiles (bundle `app/data/growth/*.csv` —
      load at import; missing CSV kills the app, REP §7.2), WHO/CDC tables,
      milestone_achievements model
- [x] `dashboard` router: aggregated health overview (scores, alerts, activity)
- [x] `household_search`: FTS5/BM25 cross-member search + `search_mirror` table
- [x] `smart_search` + `smart_entry` routers: NL query → structured answer;
      quick-add parsing (text-only; no voice until Phase 11's whisper dep)
- [x] `database` router: integrity card endpoint (`PRAGMA integrity_check`,
      orphan scan)
- [x] `fhir_import` + `health_import` (Apple Health export XML ingest)
- [x] Records: dedup/merge endpoints (merge two records, content-hash duplicate
      detection), `confidentiality_level` (household|caregiver|private) with
      role-ceiling enforcement, batch extract SSE

Frontend:
- [x] Member page tabs to full 6-tab layout: Overview / Records / Trends /
      Journal (symptoms+vaccinations+growth+milestones) / Safety (allergies+
      conflicts) / Conditions — each in a TabErrorBoundary
- [x] Growth chart (percentile bands) on member page
- [x] `/data-hygiene` page: duplicate scan + merge wizard
- [x] Dashboard page (`home.tsx`): smart-entry bar, alert strip, family strip,
      quick actions, health overview, activity feed, radar chart
- [x] Record wizard (type → visit → clinical → review) + classic form;
      batch upload with chunked SSE reassembly
- [x] Confidentiality badge + enforcement in UI

Tests: allergy-conflict unit tests; growth percentile math vs CDC reference
vectors; merge idempotency; FHIR/Apple Health fixture imports. Gate e2e in
`tests/test_phase10_gate.py`.

Gate: e2e — upload record → extract → flag duplicate → merge; add allergy →
prescribe conflicting med → conflict surfaces on Safety tab. **PASSED.**

## Phase 11 — AI tools suite ✅ (REP §4.6 AI, §4.7)

Backend:
- [x] Extend `reports.py` to the full insight family: consultant_note,
      consolidated_report, medication_report, medication_schedule, forecast
      (+ health_qa on ai_insights; per-kind deterministic snapshots)
- [x] `member_drug_interactions`: interaction analysis across member's meds
- [x] `member_drug_info`: openFDA lookup (`OPENFDA_API_KEY`, RxNorm fallback,
      AI generic-name fallback)
- [x] `member_resources`: MedlinePlus Connect / DailyMed / Health Canada DPD /
      MHRA lookups (metadata only, single top hit)
- [x] `member_preventive`: preventive-care recommendations + dismissals
- [x] `ai_insights` router: standalone insights + verification polling
- [x] `health_alerts`: lab anomaly alerts at the extraction boundary
- [x] `reference_ranges`: extended with citations
- [x] `jan_aushadhi` router + `local_drugs` table + bundled **official PMBJP
      export** (2,445 products; seed via `uv run python -m
      app.scripts.seed_jan_aushadhi`, refresh via `JAN_AUSHADHI_CSV`)
- [x] Shared insight infrastructure: `CLINICAL_WRITING_STYLE`, Pydantic-
      rendered JSON schemas in prompts, deterministic stats computed in code
- [x] Voice memos: local-only faster-whisper (optional dep → 501 + install
      hint; `WHISPER_MODEL_SIZE`), transcription-only (nothing persisted)
- [x] CMDT-style grounding: FTS5 index + metadata-only citations invariant

Frontend:
- [x] `/ai-tools` hub + tool pages: smart-entry, smart-report, pre-consultation,
      drug-interactions, consultant-note, consolidated-report, summaries,
      medication-report
- [x] Verification badges + polling UI shared across tools (verifier model shown)
- [x] Chat upgrades: citation rendering, compendium lookup panel
- [x] Voice mic button on smart-entry (MediaRecorder → transcribe → text box)

Tests: per-kind insight tests (grounding numbers asserted in prompts — the
phase-4 F1 eval harness covers extraction); drug-info mock tests; voice
501-without-whisper test. Gate: consolidated report grounded in DB values
(`tests/test_phase11_12_gate.py`). **PASSED.**

## Phase 12 — Ops, jobs & PWA ✅ (REP §4.8, §5.5)

Backend — complete the scheduler job set (v2 has missed-dose sweep, reminder
dispatch, token prune):
- [x] `check_refill_alerts` (daily), `rotate_backups` (daily, 30-day retention),
      `weekly_digest`, `dispatch_web_push` watermark pruning,
      `check_ai_providers` (15-min probes → router circuit breaker via shared
      cache), `detect_anomalies` (6 h), `cleanup_staging` (hourly),
      `verify_file_integrity` (daily), `backup_database` hourly tick
      self-gated on household schedule (online-backup + encrypted tar)
- [x] Single-instance scheduler guard (fcntl lock on `data/scheduler.lock`)
- [x] Middleware parity: GZip, RequestId echo, SecurityHeaders (CSP, HSTS in
      prod), tiered request-size limiter + sliding-window rate limiters
      (general 100/60s, auth 10/60s) — in-memory default, Redis via
      `REDIS_URL` with permanent graceful fallback on outage
- [x] `/health`, `/health/ready` (DB + storage write probe), `/health/detail`
      (x-health-key)

Frontend:
- [x] PWA: `manifest.json` + hand-rolled `sw.js` (API never cached;
      navigation network-first; assets cache-first; no-`skipWaiting` update
      toast flow); SW unregistered in the Tauri shell
- [x] Offline banner in AppLayout
- [x] Themes: light/sepia/grey/dark with anti-flash inline script + cookie
      mirror; Settings → General swatches
- [x] i18n: typed dictionary (`en` + `pt` pilot), `useI18n()` (nav/settings
      surfaces; rest of app adopts as touched)
- [x] Settings → Data tab: backup/restore UI + DB integrity card (no reset
      endpoint exists — reset dialog omitted)

Tests: job idempotency (double-run safe), rate-limiter integration, backup
round-trip restore, theme/SW/i18n unit tests.

Gate: theme persists (unit-tested; e2e in phase 13 suite); PWA update toast
(hook-tested); nightly backup archive appears and restores
(`tests/test_phase11_12_gate.py`). **PASSED.**

## Phase 13 — Quality floors & release engineering ✅ (REP §4.9, §5.6, §9)

- [x] Backend coverage ratchet (CI-gated floor; "raise, never lower") —
      measured 89% post-phase-10 → floor 88 (`--cov-fail-under`, CI + make coverage)
- [x] Frontend vitest coverage thresholds — whole-tree counting like upstream,
      measured 14% → floors 1pt under (`vitest.config.ts` thresholds)
- [x] Playwright suite growth: auth (incl. 2FA via inline RFC-6238 TOTP),
      navigation + member tabs, members, record wizard vs classic, extraction
      (graceful no-AI degradation), notifications (scheduler job as one-shot),
      backup/restore, member delete, smoke, axe-core accessibility — 10 spec
      files / 27 tests green; no serious/critical axe violations
- [x] `make sync-version`: pyproject → frontend/package.json + Cargo.toml +
      tauri.conf.json (packaging/sync-version.sh, --dry-run supported)
- [x] Updater: sign with `TAURI_SIGNING_PRIVATE_KEY` → `.deb.sig`;
      `packaging/update-manifest.sh` → `latest.json`; `FHM_UPDATE_MANIFEST_URL/
      _PUBKEY` env-gated (inert when unset; cargo check passes). Also fixed a
      pre-existing blocker: desktop/Cargo.toml declared edition 2026 (no
      toolchain supports it) → 2024
- [x] Release checklist: docs/RELEASE.md (bump → sync → debs → optional
      manifest); CI workflow with version-consistency + quality gates + deb build

Gate: full suite green — pytest 269 (+coverage floor), vitest 75 (+thresholds),
Playwright 27 (+axe clean). Both .debs build from clean tree
(`cargo check` green; full tauri build requires the packaging toolchain).

---

## Cross-cutting invariants (apply to every phase — REP §10)

1. Tailwind v4 CSS-first theming; `html2canvas-pro` for PDF export (oklch).
2. Cookie auth end-to-end; `isAuthenticated()` stays a `true` stub.
3. SSE only — no WebSockets; heartbeat frames + aclose-on-disconnect.
4. `ENCRYPTION_KEY` independent of `SECRET_KEY`; PHI columns via `EncryptedText`.
5. SQLite `foreign_keys=OFF` is deliberate — don't fix.
6. Every Alembic migration idempotent (SQLite upgrades on every boot); never
   edit shipped migrations.
7. All fetches through `src/lib/api-client.ts`; new tables re-exported from
   `app/models/__init__.py`.
8. Test auth rides the httpx cookie jar; AI calls patched at module-scope
   callables (never reach real providers in tests).
9. New code carries its coverage (ratchets rise, never fall).

## Suggested order & dependencies

- 8 → 9 → 10 (role ceiling + confidentiality needs roles from 8; Safety tab
  needs allergy model wiring from 10; dashboard needs domains from 9+10).
- 11 depends on 10 (insights aggregate labs/vitals/conditions).
- 12 can run parallel to 9–11 (mostly backend jobs + shell polish).
- 13 is continuous — raise ratchets at the end of each phase.
