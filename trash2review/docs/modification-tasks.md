# Modification Tasks

Derived from `docs/modification-plan.md`. Implemented 2026-11-03 on
`feature/medicine-entry-ai-tab`; checkboxes mark state after that work.

## 1. Navigation — relocate "AI Reports" into "AI Tools" ✅ (prior work verified)

- [x] 1.1 Audit — commit 3d29419 already moved generation into `/ai-tools`; no standalone `/reports` route remains in `router.tsx` or the sidebar.
- [x] 1.2 Nothing left to remove — member overview's `ReportsSection` is a link surface into the tools (by design).
- [x] 1.3 No new strings needed.
- [x] 1.4 Verified: no dead links; all five report tools resolve inside `/ai-tools`.

## 2. Localization — English, Tamil, Hindi ✅

- [x] 2.1 `frontend/src/lib/i18n/ta.ts` and `hi.ts` added (typed against `Dictionary`).
- [x] 2.2 Registered in `frontend/src/lib/i18n/index.tsx` (`Language`, `LANGUAGES`, `DICTIONARIES`, navigator prefixes `ta`/`hi`).
- [x] 2.3 Language picker needed no change — settings general section maps `LANGUAGES`.
- [x] 2.4 Persistence was already in place (localStorage + mirror cookie).
- [ ] 2.5 Full hardcoded-string audit — deferred; i18n is documented pilot scope (see `en.ts` header). New surfaces adopt the dictionary as they are touched.
- [x] 2.6 Tamil/Devanagari font fallbacks added to `globals.css` body.
- [x] Tests: `resolveInitialLanguage` ta/hi cases + dictionary rendering in `i18n.test.tsx`.

## 3. UX/UI — Esc as global cancel/back shortcut ✅ (prior work + tests)

- [x] 3.1 Verified: `lib/esc-stack.ts` + `use-esc-close.ts`/`use-escape-navigation.ts` (commit a54fd24) cover overlays then back-nav; wizard and member-edit dialog route through the stack.
- [x] 3.2 Covered by existing `esc-stack.test.ts` and `member-edit-dialog.test.tsx` (Esc close asserted).

## 4. Content Quality — concise, professional AI-generated text ✅

- [x] 4.1 `TONE_DIRECTIVE` added in `backend/app/services/insight_service.py` (the declared single source of truth) and composed into `CLINICAL_WRITING_STYLE`.
- [x] 4.2 Reports get it via `REPORT_SYSTEM` (composes `CLINICAL_WRITING_STYLE`).
- [x] 4.3 Insights get it via the shared style; chat `CHAT_SYSTEM` and smart-entry `PARSE_SYSTEM` given explicit brevity/professional-tone lines.
- [x] 4.4 `prompts/extraction.md` rule 7: summary ≤ 3 sentences, findings only.
- [ ] 4.5 Live-output spot-check — needs a real provider; not runnable in tests (fakes only). Do this with `./dev.sh` once a provider is configured.

## 5. Medicine Module — streamline entry and display ✅

- [x] 5.1 `AddMedicationForm` now collapsed behind an "Add medicine" toggle (same aria-expanded pattern as vaccinations/conditions); Prescribed by / Duration / Start date moved under a "+ More options" disclosure. Core path: name, dosage, timing, dose times, schedule.
- [x] 5.2 List/cards audited — rows already lead with name + schedule badge + one summary line; pillbox owns next-dose. No change needed.
- [x] 5.3 Smart entry audited — drafts are read-only (medicine/dosage/timing), no duplicated form steps.
- [x] 5.4 Full vitest suite green; new `medication-manager.test.tsx` covers toggle, disclosure, create-and-collapse.

## 6. Member Onboarding — current medications + prescription update prompt ✅

- [x] 6.1 `FamilyMember.current_medications` (EncryptedText) + migration `d8e9f0a1b2c3` (existence-guarded, after `c8d9e0f1a2b3`).
- [x] 6.2 Exposed via `MemberUpdate`/`MemberResponse` (PATCH setattr flow — no router change needed).
- [x] 6.3 Field added to `member-edit-dialog.tsx` (create form stays minimal by design).
- [x] 6.4 `CurrentMedicationsPrompt` on prescription record pages: "Merge with tracked medications" → `POST /members/{id}/current-medications/merge` (AI merge of existing free-text + active `Medication` rows) → editable suggestion → PATCH on save; dismiss supported. Nothing persisted until the user accepts.
- [x] 6.5 Tests: `backend/tests/test_modifications.py` (round-trip, merge suggestion, 503 without provider) + `current-medications-prompt.test.tsx` (merge/edit/save, dismiss, error).

## 7. Prescription Integration — merge with doctor visits + auto-fill ✅

- [x] 7.1 Flow mapped: `RecordType.prescription` / `doctor_visit` exist; no prior link; `Medication.record_id` is the only implicit tie.
- [x] 7.2 Link rule in `backend/app/services/visit_link.py`: nearest `doctor_visit` within ±7 days (`VISIT_LINK_DAYS`), same member; standalone otherwise.
- [x] 7.3 Auto-fill: prescriptions fill empty `doctor_name` / `provider_id` / `diagnosis` from the linked visit (never overwrites). Wired into manual creation (`records.py`) and batch extraction; batch upload now classifies docs containing medications as `prescription` instead of `other`.
- [x] 7.4 UI: wizard visit step shows a `VisitLinkHint` for prescriptions (linked visit + auto-fill notice, or standalone notice). Upload side: batch-extracted prescriptions are classified and auto-filled server-side; an explicit "create a visit from this prescription" builder was not added — extraction's diagnosis/doctor fields already land on the linked record.
- [x] 7.5 Tests: `test_modifications.py` — autofill, standalone fallback, no-overwrite, member scoping; existing `test_batch_extract.py` still green.

## 8. Branding — replace app logo ✅

- [x] 8.1 `media/logo-0.svg` → `frontend/public/icons/icon.svg` (transparent artwork).
- [x] 8.2 New `AppLogo` component replaces the HeartPulse brand chip in sidebar, header (mobile), auth form, and public-share page.
- [x] 8.3 Favicon (`icon.svg`) + PWA `icon-maskable.svg` regenerated (full-bleed `#f7f8f9`, artwork in the 80% safe zone). Desktop packaging is Phase 6 — untouched.
- [x] 8.4 Old icon artwork replaced in place; `media/` kept as source material.

## 9. Medicine Display — schedule table with export + print (2026-11-04)

- [x] 9.1 `MedicationManager` reworked into the v1-style schedule table:
      Type | Medicine (name + dosage) | one column per dose slot in use |
      Food | Duration | Rx by | Edit/Delete. `Pillbox` and the inline
      `MedicineScheduleCard` removed from the page — the table is the only
      on-screen display; no data was deleted (UI-only change).
- [x] 9.2 Per-row Edit: new `EditMedicationDialog` (prefilled, PATCH).
      Backend `MedicationUpdate` widened (medicine, dose_form, dosage,
      timing, duration_days, start/end, status, provider_name, slots,
      slot_times); renaming recomputes `medicine_key`; slot edits merge
      into `schedule_json` preserving taper/cycle params
      (`merge_schedule_update` in `schemas/medication.py`).
- [x] 9.3 Export: `ExportMedicinesButton` downloads the table as CSV
      (per-slot time columns) via the shared `downloadCsv`.
- [x] 9.4 Print: the grouped-by-time print route (`/members/:id/medicine-schedule`)
      is unchanged and already ends at the table — footer message removed
      earlier per the Drug Schedule PDF annotation.
- [x] 9.5 Add form gained a Type (dose form) select and a Food field.
- [x] 9.6 Tests: backend `test_health_tracking.py` (widened PATCH, slot
      merge with taper params, slot validation) + frontend
      `medication-manager.test.tsx` (table columns, edit-dialog PATCH).

## 10. Milestones — infants and children only (2026-11-04)

- [x] 10.1 `MilestonesCard` renders only when the member has an age
      under 72 months (reference set ends at 48 months); hides for adults
      and members without a birth date. Backend annotations unchanged.
- [x] 10.2 Test: `milestones-card.test.tsx` (young child renders, adult
      hidden, no-DOB hidden).

## 11. Vaccinations — IAP-ACVIP 2025 schedule (2026-11-04)

- [x] 11.1 `RULES` in `immunization_service.py` upgraded from the bare
      UIP list to the IAP-ACVIP Immunization Timetable 2025 (Indian
      Pediatrics 2026;63:311-324) layered over UIP: adds Hib, influenza
      (6mo/7mo/annual), typhoid conjugate, hepatitis A, MMR-2/3, varicella,
      PCV booster, Hib/IPV boosters, Tdap (10y), HPV (9y), meningococcal
      and cholera (special/endemic situations, labelled as such).
- [x] 11.2 Source/verification header updated (last verified 2026-11-04);
      disclaimer on the schedule response now names the IAP timetable.
- [x] 11.3 Catch-up math unchanged (`due = max(birth+min_age, prev+interval)`);
      match fragments stay lowercase-alphanumeric for the name matcher.
- [x] 11.4 Known matcher limitations (documented, by design): one logged
      row completes one dose slot in schedule order, so dose-specific
      names ("MMR 2") are matched by numbered fragments; combination
      records ("Pentavalent 1") match DTP/HepB via numbered fragments but
      not Hib (separate antigen).

## Known issues / follow-ups

- `backend/tests/test_ops_jobs.py::test_scheduler_lock_exclusive_and_lazy`
  fails on a clean checkout in this environment (stale lock file) —
  pre-existing, unrelated to this work.
- 2.5 (full string audit) and 4.5 (live tone spot-check) intentionally
  deferred; see notes above.
