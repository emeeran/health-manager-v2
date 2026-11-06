# Style Plan — Phase 3

Detected conventions (from configured tools + oldest files), decisions, and
what was applied.

| # | Convention | Winner | Action |
|---|---|---|---|
| 1 | Python formatting | ruff format (project's configured tool, pyproject `[tool.ruff]`) | Applied repo-wide (154 files drifted). Commit 22e2162. |
| 2 | TS/TSX formatting | prettier (package.json `format` script) | Applied repo-wide (79 files drifted). Commit 5bc19a2. |
| 3 | Line length | backend 100 (pyproject); prettier defaults | unchanged |
| 4 | Error handling | exceptions everywhere: backend raises HTTPException/ValueError; frontend throws ApiError. Graceful-degradation excepts exist only where documented as deliberate (provider probes, health detail, push best-effort). | Consistent — no action |
| 5 | AI voice in output | none found — zero emoji/exclamation in logs, errors, or docs | no action |
| 6 | Naming | no utils/helpers dumping grounds in app code; `Manager` suffix only on MedicationManager (a genuinely stateful UI component). verb-first functions throughout | no action |
| 7 | Docstrings/comments | terse, why-focused, em-dash asides; consistently so repo-wide | no action |
| 8 | Import order | stdlib → third-party → app, consistent grouping (verified across routers/services) | no action |
| 9 | Config knobs | every Settings field has a real reader (checked in Phase 2 scan) | no action |
| 10 | prompts/README.md | promised a transcription_report.md that never landed | rewritten to describe actual contents |
| 11 | eslint `_node` error | codebase precedent is inline `eslint-disable-next-line` with `--` rationale (record-detail.tsx:805) | matched precedent |
| 12 | Tests | all substantive; no padding/auto-generated names found | no action |

Deliberately not done:
- ruff format was NOT config-tuned to preserve the manual ~88-col wrap habit;
  the project's own line-length=100 config won (boring: use the tool as configured).
- packaging/build-deb.sh `rm -rf .../prompts/p*` no-op left alone — packaging/
  is Phase-6 territory per CLAUDE.md; logged in AUDIT.md instead.

Post-apply verification: ruff lint clean, mypy unchanged (1 pre-existing
error), backend 306 passed / 1 known env failure, eslint clean, tsc clean,
vitest 119 passed.
