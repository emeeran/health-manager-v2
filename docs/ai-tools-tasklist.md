---
title: "AI Tools: Implementation & Testing Task List"
date: 2026-11-07
tags:
  - tasklist
  - ai-tools
  - reports
  - drug-info
  - health-manager
  - testing
status: completed
---

# AI Tools: Implementation & Testing Task List

Related docs: [[ai-tools-implementation-plan]] | [[modification-idea]] | [[PLAN]] | [[TASKLIST]]

Approved plan: `docs/ai-tools-implementation-plan.md` (2026-11-07). Decisions:
D1 grounded price narrative · D2 upgrade `pre_consultation` in place, A5
structured only · C1 scheduled catalog refresh (inert until dataset URL found) ·
C2 WhatsApp text export · C3 no prose for pre_consultation.

---

## 1. Overview & Scope

Five new/changed AI tools on top of the Phase 7 report machinery, one branch
`feature/ai-tools-reports`, one conventional commit per task group.

- **WS1** Doctor Visit Summary — new `visit_summary` kind + visit picker
- **WS2** Pair drug interaction — new endpoint + form page
- **WS3** Drug info — UI card over existing backend
- **WS4** Price comparison — deterministic table + grounded narrative + catalog refresh job
- **WS5** Pre-consultation A5 — in-place structured upgrade, print + WhatsApp export
- **WS6** Health Insights export/print

Invariants: model narrates, never invents numbers; `render_schema_block()` +
Pydantic validation; PHI consent gating; insights persist; print via
`window.print()`; all fetches through `lib/api-client.ts`.

---

## 2. Task Breakdown

### Phase 0: Branch & Prep 🌱
- [x] **Create branch**: `git checkout -b feature/ai-tools-reports` off `main`.
- [x] **Baseline green**: `cd backend && uv run pytest` (deselect the
      scheduler-lock test — dev server may hold the lock) and
      `cd frontend && npx tsc --noEmit && npx vitest run` before any change.

### Phase 1: WS1 — Doctor Visit Summary 🩺
- [x] **Snapshot builder**: `snapshot_visit_summary(member, record_id)` in
      `backend/app/services/report_service.py` — patient info, reason,
      diagnosis, treatment plan (linked `Medication` rows +
      `investigations`/`prescription_text`), doctor's notes, follow-up.
- [x] **Prompt**: add §4.1 template to `PROMPTS` (key `visit_summary`).
- [x] **Route**: `record_id` query param on the stream route; 422
      `record_id required for visit_summary` when absent; register kind +
      slug `visit-summary` in `routers/reports.py`.
- [x] **Frontend**: register kind in `lib/types/insight.ts` + card in
      `lib/ai-tools.ts` (group: Reports); visit picker page
      `pages/ai-tools/visit-summary.tsx` (doctor_visit records, latest first)
      + route in `router.tsx`.
- [x] **Tests**: snapshot with/without linked meds+labs; 422 without
      `record_id`; streaming happy path (FakeProvider).

### Phase 2: WS2 — Pair Drug Interaction 💊
- [x] **Service**: `check_pair(medicine_a, medicine_b)` in
      `services/drug_interaction_service.py` reusing `INTERACTION_PROMPT`
      (template §4.2); no member medication data.
- [x] **Route**: `POST /api/v1/drug-interactions/pair` body
      `{medicine_a, medicine_b}`; 422 on missing names; persists
      `Insight kind="drug_interactions_pair"`.
- [x] **Frontend**: `pages/ai-tools/drug-interaction-pair.tsx` — two
      autocomplete inputs (member meds + Jan Aushadhi names), streaming
      result; card in group Medicine Reports.
- [x] **Tests**: validation, prompt contains both names, insight persisted.

### Phase 3: WS3 — Drug Info Card 📋
- [x] **Frontend**: `pages/ai-tools/drug-info.tsx` — medicine autocomplete →
      `GET /members/{id}/drug-info?medicine=` → structured sections with
      source badge (openFDA / RxNorm / AI); card in Medicine Reports.
- [x] **Tests**: vitest for result rendering + error path (unknown medicine).

### Phase 4: WS4 — Price Comparison 💰
- [x] **Service**: `compare_prices(names)` in `services/local_drug_service.py`
      — exact `medicine_key` → composition → fuzzy matching; rows: brand,
      manufacturer, composition, pack, price, match quality; unmatched →
      `match: null`.
- [x] **Route**: `POST /api/v1/drugs/price-compare` body
      `{medicines: [..], narrate: bool = true}`; max 15 → 422; default =
      member's active medications.
- [x] **Narrative (D1)**: grounded second AI call — table JSON as sole ground
      truth, template §4.4; facts outside the table forbidden.
- [x] **Frontend**: `pages/ai-tools/price-comparison.tsx` — editable medicine
      list (pre-filled from active meds), table + total, Print/Save PDF,
      CSV export; caption *"Reference prices from Jan Aushadhi catalog;
      actual retail prices vary."*; card in Medicine Reports.
- [x] **Catalog refresh job (C1)**: `refresh_catalog()` +
      scheduler job; config `JAN_AUSHADHI_DATASET_URL` /
      `JAN_AUSHADHI_REFRESH_DAYS` (30); fetch failure or unset URL → log and
      keep existing rows. Search for a stable public dataset URL; if none,
      ship inert and document the bundled-CSV re-seed command.
- [x] **Tests**: matching tiers; max-15; empty catalog; narrative prompt
      receives table JSON; refresh job success/failure/unset-URL.

### Phase 5: WS5 — Pre-consultation A5 📝
- [x] **Schema**: `PreConsultationA5` (date, member_name,
      chronic_conditions, chief_complaints, to_discuss 3–5,
      current_medications) — template §4.3.
- [x] **Upgrade in place (D2/C3)**: replace `pre_consultation` prompt with the
      schema prompt (`render_schema_block`); validated payload →
      `sources_json`; prose path removed; kind/slug unchanged.
- [x] **Render**: structured mode in `components/ai-tools/insight-tool.tsx`
      (markdown path untouched for other kinds).
- [x] **Print**: field preview + inline editing of `to_discuss`; print route
      outside `AppLayout`; `@page { size: A5; margin: 12mm }`.
- [x] **WhatsApp export (C2)**: "Copy for WhatsApp" + `.txt` download of the
      plain-text rendering (plan §WS5).
- [x] **Tests**: schema-valid payload in `sources_json`; local-only provider
      when consent off; vitest for A5 field rendering + WhatsApp text builder.

### Phase 6: WS6 — Health Insights Export/Print 🖨️
- [x] **Print**: print route for `InsightView` markdown (shared print palette).
- [x] **Export**: copy markdown + download `.md` (`lib/export.ts` gains
      `downloadText`).

### Phase 7: Verification & Merge ✅
- [x] **Backend suite**: `cd backend && uv run pytest` green.
- [x] **Lint**: `uv run ruff check --fix .`; frontend `tsc --noEmit` + vitest.
- [x] **Live check** (Ollama running): generate visit_summary, pair
      interaction, price table + narrative, pre-consultation A5 print view;
      confirm `Insight` rows in the summaries history browser.
- [x] **Merge**: conventional commits per phase; version bump
      `chore: bump version to 1.4.0` in `backend/pyproject.toml`; merge to
      `main` after review.

---

## 3. Completion Notes (2026-11-07)

All phases implemented on `feature/ai-tools-reports`; backend 371 tests and
frontend 137 tests + `tsc` + `vite build` green.

**Live verification (real provider, isolated smoke instance):** visit_summary
stream (per-visit sections, "Not documented" honored), pre_consultation A5
note (structured_ok True, date code-stamped), pair interaction (grounded,
consent-gated), price-compare table + grounded narrative (unmatched medicines
reported, no invented prices), insight persistence (price_comparison rows).

**Fixes found during live verification:**
- Partial price matching reworked to word-prefix scoring — a substring match
  had surfaced "Acarbose + Metformin" combos (₹77.81) for a plain metformin
  query; now resolves to the actual metformin product (₹3.75).
- A5 note `date`/`member_name` are code-stamped: the model returned `null`
  and hallucinated dates; the app always owns those two fields.

**Deferred:** `JAN_AUSHADHI_DATASET_URL` remains unset — the scheduled catalog
refresh ships wired but inert (no stable public dataset URL verified); manual
re-seed: `uv run python -m app.scripts.seed_jan_aushadhi`.
