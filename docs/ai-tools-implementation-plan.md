# AI Tools — Implementation Plan (for review)

Source idea: `docs/modification-idea.md` · Earlier draft: `docs/Modification-plan.md`
Status: **approved 2026-11-07** (D1/D2 resolved — see §6) · Contracts: `docs/PLAN.md` (pinned) · Tasks: `docs/ai-tools-tasklist.md`

## 1. Gap analysis — idea vs. current state

Much of the idea already ships (Phase 7). Remaining work is smaller than it looks:

| # | Idea tool | Current state | Work needed |
| --- | --- | --- | --- |
| 1 | Health Insights | ✅ `health_insights` report kind<br>ADD export/print | Template retained; add export/print (WS6) |
| 2 | Doctor Visit Summary | ❌ No single-visit kind (`consolidated_report` is a ledger, not per-visit) | New `visit_summary` kind + visit picker |
| 3a | Interaction — currently taking | ✅ `drug_interactions` insight (`routers/member_drug_interactions.py`) | UI only: AI Tools card + link |
| 3b | Interaction — any two | ❌ Missing | New pair endpoint + form page |
| 3c | Complete info on a medicine | ✅ Backend (`routers/member_drug_info.py`: openFDA → RxNorm → AI) | UI only: AI Tools card + result page |
| 3d | Price comparison table | ❌ Missing (Jan Aushadhi catalog with prices exists: `models/local_drug.py`) | New deterministic endpoint + table UI |
| 4 | Pre-consultation Note | ✅ `pre_consultation` report kind (prose)<br>ADD print/share | In-place upgrade: A5 structured only + WhatsApp text export (WS5) |

## 2. Principles carried over (non-negotiable)

- **The model narrates, never invents numbers** — all facts computed in code, passed as JSON ground truth (`report_service.py` invariant).
- Prompts render a Pydantic schema block (`render_schema_block()`); the same model validates the reply — prompt/parser cannot drift.
- PHI consent gating: `member.cloud_ai_consent` false → local-only providers.
- Every generation persists as an `Insight` row → history browser works for free.
- Print via browser `window.print()` + `@media print` (existing pattern; no backend PDF).
- All frontend fetches via `lib/api-client.ts`; SSE via `lib/api/sse.ts`.

## 3. Workstreams

### WS1 — Doctor Visit Summary (`visit_summary`)

Per-visit report: user picks one `doctor_visit` record; snapshot is built from that record + linked medications/labs, then narrated.

**Backend** (follow the 4-step registration recipe):

- `services/report_service.py`: `snapshot_visit_summary(member, record_id)` in
  `SNAPSHOT_BUILDERS` — patient info (member + medical history), reason (record `clinical_data`/`summary`), diagnosis, treatment plan (linked `Medication` rows + `investigations`/`prescription_text`), doctor's notes, follow-up.
- Stream route gains an optional `record_id` query param; when the kind requires a visit and none is given → `422 {"detail": "record_id required for visit_summary"}`.
- `routers/reports.py`: add to `VALID_KINDS` / `KIND_SLUGS` (`visit-summary`).

**Frontend:**

- `lib/types/insight.ts`, `lib/ai-tools.ts`: register kind + card (group: Reports).
- `pages/ai-tools/visit-summary.tsx`: thin page wrapping `AiToolPage` with a visit picker (dropdown of the member's `record_type=doctor_visit` records, latest first) that sets `record_id` before streaming.

### WS2 — Interaction Report: any two medicines

**Backend:**

- `services/drug_interaction_service.py`: `check_pair(medicine_a, medicine_b)` —
  reuses `INTERACTION_PROMPT` with a two-drug slot; no member medication data.
- `routers/member_drug_interactions.py`: `POST /api/v1/drug-interactions/pair `body `{medicine_a, medicine_b}` (member route kept for auth context; both names required, 422 otherwise). Persists as `Insight  kind="drug_interactions_pair"`.

**Frontend:**
- `pages/ai-tools/drug-interaction-pair.tsx`: two autocomplete inputs (seeded from
  the member's medications + Jan Aushadhi names), "Check interaction" → streams result.
- Card in group **Medicine Reports**.

### WS3 — Complete info on a medicine (UI only)

- `pages/ai-tools/drug-info.tsx`: medicine autocomplete → `GET
  /members/{id}/drug-info?medicine=` → render structured sections (class, uses,
  dosing, side effects, warnings) with source badge (openFDA / RxNorm / AI).
- Card in group **Medicine Reports**.

### WS4 — Price comparison table (deterministic, no AI)

Prices come only from the seeded Jan Aushadhi catalog, kept fresh by a scheduled
refresh job — the table itself is code-built, never a model claim. An optional
AI narrative is allowed but must be **grounded in the computed table only** (D1).

**Backend:**
- `services/local_drug_service.py`: `compare_prices(names: list[str])` — match each
  name via existing `search_local_drugs` (exact `medicine_key` → composition match →
  fuzzy); return per-medicine rows: brand, manufacturer, composition, pack, price,
  match quality; unmatched names returned with `match: null`.
- `routers/jan_aushadhi.py`: `POST /api/v1/drugs/price-compare` body
  `{medicines: [..], narrate: bool = true}` (max 15 → 422 above), default set =
  member's active medications when body omitted. With `narrate=true`, a second AI
  call runs **after** the table is computed; its prompt receives the table JSON as
  sole ground truth (template §4.4) and may only state facts present in it
  (e.g. cheapest equivalent by composition, total per-composition savings).
- Catalog refresh (scheduled): new job in the Phase 7 scheduler — fetches the
  published Jan Aushadhi dataset and re-seeds `local_drugs`
  (`services/local_drug_service.py:refresh_catalog()`); new config
  `JAN_AUSHADHI_DATASET_URL` + `JAN_AUSHADHI_REFRESH_DAYS` (default 30). When the
  URL is unset or the fetch fails, the job logs and keeps the existing rows —
  catalog availability never regresses.
  ⚠️ Dependency: no stable public dataset URL is confirmed yet; if none is found
  at implementation time the job ships wired but inert (URL unset) and re-seed
  stays the bundled-CSV command.

**Frontend:**
- `pages/ai-tools/price-comparison.tsx`: editable medicine list (pre-filled from
  active meds) → table (medicine, brand, manufacturer, composition, pack, price) +
  total; "Print / Save PDF" like the medicine schedule; CSV export via `lib/export.ts`.
- Fixed caption: *"Reference prices from Jan Aushadhi catalog; actual retail prices vary."*
- Card in group **Medicine Reports**.

### WS5 — Pre-consultation Note: A5 structured output, print + WhatsApp share

Upgrade the **existing `pre_consultation` kind in place** (decision D2): the
prose narrative is dropped; the model returns the validated structured A5 payload
(template §4.3) and the UI renders it field-by-field.

**Backend:**
- `services/report_service.py`: replace the `snapshot_pre_consultation` prompt with
  the §4.3 schema prompt rendered via `render_schema_block(PreConsultationA5)`; the
  validated Pydantic payload is stored in `sources_json` (prose path removed).
- Kind and slug unchanged: `pre_consultation` / `pre-consultation`.

**Frontend:**
- `components/ai-tools/insight-tool.tsx`: structured render mode when the kind's
  `sources_json` carries the A5 payload (markdown path stays for other kinds).
- `pages/ai-tools/pre-consultation.tsx`: generate → field preview with inline
  editing of the generated `to_discuss` items → **"Print (A5)"** → dedicated print
  route (outside `AppLayout`, pattern from `pages/medicine-schedule.tsx`) with
  `@page { size: A5; margin: 12mm }`; **"Copy for WhatsApp"** / `.txt` download of
  the plain-text rendering below.
- A5 sheet template (from the idea doc):

```
┌──────────────────────────────────────┐
│  Date: 2026-11-06                    │
│  Member Name: Meeran                 │
│  Chronic: T2D, HTN, PD               │
│                                      │
│  C/c: chest discomfort on exertion;  │
│       palpitations at night          │
│                                      │
│  To discuss with doctor              │
│   1. Symptom progression since last  │
│      visit                           │
│   2. Switch Met XL → CardiCare?      │
│   3. Dose titration up to 10 mg      │
│   (3–5 items; editable before print) │
│                                      │
│  Current medications: … (compact)    │
└──────────────────────────────────────┘
```

- WhatsApp text export (same content, plain text):

```text
Date: 2026-11-06
Member Name: Meeran
Chronic: T2D, HTN, PD

C/c: chest discomfort on exertion; palpitations at night

To discuss with doctor
1. Symptom progression since last visit
2. Switch Met XL → CardiCare?
3. Dose titration up to 10 mg

Current medications: Met XL 25mg OD, …
```

### WS6 — Health Insights: export / print

Template unchanged (per the idea doc). Add output only:

- `components/ai-tools/insight-tool.tsx`: "Print" action on `InsightView` —
  dedicated print route outside `AppLayout` rendering the markdown report with the
  shared `@media print` palette (pattern from `pages/medicine-schedule.tsx`).
- "Export": client-side — copy markdown to clipboard + download `.md`
  (`lib/export.ts` gains `downloadText`).

## 4. Templates

### 4.1 `visit_summary` prompt

```text
You are preparing a Doctor Visit Summary for {member}.

GROUND TRUTH (JSON) — verified app data. Narrate only from it; never invent or
alter names, doses, dates, or values. Where a section has no data, write
"Not documented".

{stats}

Write exactly these sections, in order:
**Patient Information** — name, age, relevant medical history.
**Reason for Visit** — symptoms or concerns addressed at this visit.
**Diagnosis** — conditions identified or ruled out.
**Treatment Plan** — prescriptions, tests, follow-up actions.
**Doctor's Notes** — observations and advice recorded at the visit.
**Follow-Up** — next steps, referrals, scheduled appointments.

{tone}{style}{citations}
```

### 4.2 Pair interaction prompt (slot into `INTERACTION_PROMPT`)

```text
Two medicines, named by the user (not necessarily in the member's record):

DRUG A: {medicine_a}
DRUG B: {medicine_b}

{member_context}

Report: interaction severity (none/minor/moderate/major), mechanism, documented
effects, and practical advice (spacing, monitoring, when to consult the doctor).
If no documented interaction exists, say so plainly — do not manufacture risk.

{schema_block}
```

### 4.3 Pre-consultation A5 — Pydantic schema + prompt

```python
class PreConsultationA5(BaseModel):
    date: str                 # ISO date of the upcoming/selected visit
    member_name: str
    chronic_conditions: list[str]   # rendered as the "Chronic:" line
    chief_complaints: list[str]   # rendered as the "C/c:" line
    to_discuss: list[str]         # 3–5 items for "To discuss with doctor"
    current_medications: list[str]  # "Drug dose" strings, compact
```

```text
You are preparing a one-page pre-consultation note for {member} that the patient
carries to the doctor.

GROUND TRUTH (JSON): {stats}

Fill the schema exactly. Rules:
- chronic_conditions: active chronic conditions from ground truth, short names.
- chief_complaints: short symptom phrases, no diagnoses you weren't given.
- to_discuss: 3–5 concrete questions/topics, most important first — include
  symptom-related points and any medication changes visible in the data
  (e.g. switches, dose changes under discussion).
- current_medications: verbatim "medicine + dosage" from ground truth, active only.
- No prose outside the schema. No invented values.

{schema_block}{tone}{style}
```

### 4.4 Price-comparison narrative prompt (grounded, D1)

Runs only after the table is computed; the table JSON is the sole ground truth.

```text
You are annotating a medicine price-comparison table for {member}.

GROUND TRUTH (JSON) — the computed table. You may state ONLY facts present in
it: cheapest option per composition, totals, unmatched medicines, match quality.
Never cite prices, brands, or availability not in the table. If the table has no
useful comparison, say so in one sentence.

{table}

Write 2–4 short sentences: the cheapest equivalent per composition (same
composition, cheapest pack adjusted per-unit where the table shows it), the
overall total, and any medicines the catalog could not match.
```

## 5. Tests (FakeProvider pattern, `tests/test_insights_family.py` as model)

- `visit_summary`: snapshot builder with/without linked meds+labs; 422 without
  `record_id`; streaming happy path.
- `drug-interactions/pair`: validation (missing names), prompt contains both names,
  insight persisted with `drug_interactions_pair`.
- `price-compare`: exact/composition/fuzzy/unmatched matching; max-15 limit;
  empty-catalog behavior; narrative prompt receives the table JSON (grounding).
- Catalog refresh job: fetch-success re-seeds; fetch-failure and unset URL keep
  existing rows; no-op logged.
- `pre_consultation`: schema-valid A5 payload stored in `sources_json`; prose
  path removed; local-only provider when consent off.
- Frontend: vitest for the visit picker, price table (match-null row rendering),
  A5 field rendering + WhatsApp text builder.

## 6. Task order (each = one conventional commit on `feature/ai-tools-*`)

1. `feat: add visit_summary report kind with per-visit picker` (WS1)
2. `feat: pair drug-interaction endpoint and tool page` (WS2)
3. `feat: drug info tool card` (WS3)
4. `feat: price comparison endpoint and table page` (WS4)
5. `feat: jan aushadhi scheduled catalog refresh job` (WS4)
6. `feat: upgrade pre_consultation to structured A5 note with print + WhatsApp export` (WS5)
7. `feat: health insights print and markdown export` (WS6)
8. `chore: bump version to 1.4.0`

**Resolved decisions (approved 2026-11-07):**

- **D1** — Price comparison: include AI narrative, **grounded in the computed
  table only** (template §4.4).
- **D2** — Pre-consultation A5: **upgrade the existing `pre_consultation` kind in
  place**; prose narrative dropped, structured A5 payload only.
- **C1** — Catalog updates: **scheduled auto-refresh** job (§WS4); ships inert
  until a stable dataset URL is confirmed.
- **C2** — "Share" = **plain-text export for WhatsApp** (copy + `.txt`).
- **C3** — `pre_consultation` becomes **A5 structured only** (no prose).
