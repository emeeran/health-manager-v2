# Implementation Plan — Modification Plan Items

Source: [modification-plan.md](modification-plan.md). Branch: `feature/modification-plan-items`.
Executed 2026-11-04 — all six items implemented; verification notes at the bottom.

---

## 0. Final state

| Plan item | Status | Outcome |
|---|---|---|
| 1. Global Esc cancel/back | ✅ | Was already wired (esc-stack + `useEscapeNavigation` in AppLayout). Added: `CompendiumLookup` closes on Esc; `/medicine-schedule` route wires `useEscapeNavigation` explicitly (outside AppLayout) |
| 2. Remove pill tracking | ✅ | Backend removed: `/adherence/log`, `/history`, sweep job + scheduler entry + `MISSED_DOSE_SWEEP_HOURS`, dashboard adherence scoring/alert, digest "doses missed", `adherence_logs` table (alembic `f0a1b2c3d4e5`), maintenance-list entry, dose `status` field. `/adherence/today` kept (schedule card data source) |
| 3. Medicines → schedule table + export/print | ✅ | Card + print route were already built; added CSV export (`lib/export.ts` + `ExportScheduleButton`, slot-ordered like the card). "Currently taking" list kept (decision #1); MedicationManager stays collapsed on the page |
| 4. New record form | ✅ | Wizard collapsed to a **single-page form**: Type\|Date / Doctor\|Reason / Investigations\|Diagnosis / Note / Attachments. Provider autocomplete from the directory (`listProviders` datalist, exact-match → `provider_id`). `investigations` is a new encrypted column on `health_records` (alembic `f2c3d4e5f6a7`); shown on record detail |
| 5. Onboarding changes | ✅ | "Currently taking" med entry removed from the form and from `MemberCreate`/create route (legacy `medications` key now ignored, not seeded). Two separate fields: **Medical history** → `medical_history`, **Family medical history** → new `family_medical_history` column (alembic `f1b2c3d4e5f6`), in that order; both also in the edit dialog |
| 6. Age-appropriate vaccines | ✅ | Already present end-to-end: India UIP rules + catch-up in `immunization_service`, `/immunizations/schedule` endpoint, `ImmunizationCard` in the journal tab (the survey had missed it). Added source + last-verified note (2026-11) to the service docstring |

## Resolved decisions (2026-11-04)

1. Keep the display-only "Currently taking" list on the medicines page — **yes, for now**.
2. Investigations — **new DB column** on records.
3. Record form — **single-page form** (no wizard steps).
4. "Medical History" vs "Family medical history" — **two fields**.

## Verification

- Backend: `uv run pytest` → 298 passed (the only excluded test,
  `test_scheduler_lock_exclusive_and_lazy`, fails while a dev-server
  instance holds `data/scheduler.lock` — environmental, unrelated).
- Frontend: `tsc --noEmit` clean, `eslint .` clean, `vitest` → 117 passed.
- Alembic: three new guarded migrations `f0a1b2c3d4e5` → `f1b2c3d4e5f6` → `f2c3d4e5f6a7`.

## Manual follow-ups

- [ ] Print the medicine schedule (`/members/{id}/medicine-schedule`) and eyeball against `docs/Drug Schedule.pdf`.
- [ ] Confirm the dev server picks up the three migrations cleanly on next boot (`alembic upgrade head` runs at startup).
- [ ] MedicationManager remains reachable for schedule editing — revisit whether it should move to member detail later.
