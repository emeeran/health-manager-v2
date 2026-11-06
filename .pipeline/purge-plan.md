# Purge Plan — Phase 1 (DRY RUN, not yet applied)

Date: 2026-11-05 · Branch: cleanup/pipeline-2026-11-05
Scan method: two parallel reference-graph audits (AST import graph for backend,
basename inbound-import scan for frontend/src) + md5 full-tree duplicate scan +
backup-filename pattern scan.

## A. Tracked files → `git mv` into `trash2review/<same-path>`

| path | reason | confidence | inbound refs |
|---|---|---|---|
| `prompts/health_insights.md` | Orphaned prompt template — only `extraction.md` is loaded via `load_prompt`; insight prompts are built in-code in `insight_service.py`. Zero grep hits repo-wide. | high | none |
| `docs/implementation-plan.md` | Completed planning doc for feature shipped 2026-11-03; not referenced by README/CLAUDE.md/CI. README lists only TASKLIST/RELEASE/PLAN under docs/. | medium | none (outside its orphaned trio) |
| `docs/modification-plan.md` | Same completed planning trio. | medium | none (trio only) |
| `docs/modification-tasks.md` | Same completed planning trio; its own header says "Implemented 2026-11-03". | medium | none (trio only) |
| `backend/.gitignore` | Provably ineffective: its single rule `docs/Drug Schedule.pdf` is anchored to `backend/` and matches only a nonexistent path. Rule will be relocated to root `.gitignore` as `/docs/Drug Schedule.pdf` in the same commit. | high | none effective |

## B. Untracked local scratch (gitignored) → plain `mv` into `trash2review/`

| path | reason | confidence | inbound refs |
|---|---|---|---|
| `docs/assets/image.jpg` | Gitignored scratch (`.gitignore:42`), referenced only by orphaned modification-plan.md | medium | none live |
| `docs/assets/.genoffice-assets.json` | genoffice skill manifest for the above | medium | none live |
| `media/health_logo.png` (836K) | Gitignored brand scratch, zero references | high | none |
| `media/logo.png` (1.6M) | Same; shipped brand mark is `frontend/public/icons/icon.svg` | high | none |
| `media/Gemini_Generated_Image_*.png` (306K) | AI-generated scratch, zero references | high | none |
| `media/logo-0.svg` | Work it documented is already done (icon copied to frontend) | medium | historical mention only |
| `media/medicine-table.jpg` | Zero references anywhere | high | none |

## C. Not moved (deliberate)

- `docs/Drug Schedule.pdf` — intentionally untracked source doc; after the
  `.gitignore` fix it becomes properly ignored instead of `??` noise.
- `backend/.coverage`, `backend/build/`, `backend/dist/`, caches, `node_modules/.vitest-cache` —
  regenerable build artifacts, already gitignored.
- `.claude/scheduled_tasks.lock` — runtime lock, untracked.
- `.pipeline/`, `trash2review/README.md` — this pipeline's own scaffolding.

## D. False positives ruled out

- Zero exact/near duplicate files among tracked sources (md5 full-tree scan;
  only empty `__init__.py` share hashes).
- No `*_old/*_v1/*.bak/*copy*` files anywhere.
- All 48 backend routers imported AND mounted; all models/schemas/services/core
  modules have ≥1 inbound import. Seed scripts are documented CLI entry points.
- Frontend `src/` fully referenced (only entry points `main.tsx`, test setup
  have zero inbound — correct).
- `desktop/`, `packaging/`, alembic chain, `frontend/src/lib/api/member.ts` all verified live.

## Post-apply verification

- Full backend + frontend test suite re-run; any breakage → `git mv` back + log here.
