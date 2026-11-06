# Family Health Manager v2 — Claude Context

Clean-room rebuild of the original health-manager. Contracts are pinned in
`docs/PLAN.md` — read it before changing API shapes, auth, or env vars.

## Key Commands
```bash
./dev.sh                       # backend + frontend dev servers
cd backend && uv run pytest    # tests
cd backend && uv run ruff check --fix .  # lint
```

## Conventions
- `uv add <pkg>` for backend deps; never pip directly.
- All fetches go through `frontend/src/lib/api-client.ts` (cookie auth,
  single-flight refresh on 401). Never add another fetch call site.
- Auth is httpOnly-cookie based — no Authorization header in frontend code.
- New tables go in `backend/app/models/` and are re-exported from
  `app/models/__init__.py` so `create_tables()` picks them up.
- Tests set env vars in `tests/conftest.py` BEFORE importing `app.main`.
- Feature branches only; conventional commits; no AI co-author trailers.
- Desktop/ and packaging/ are Phase 6 — don't populate early.
