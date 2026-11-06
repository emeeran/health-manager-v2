# trash2review — holding pen, not a deletion

Files moved here by the cleanup pipeline (2026-11-05) were judged redundant or
dead, but nothing is hard-deleted. Everything keeps its original relative path
under this folder.

## Review workflow

- Inspect each file; if you disagree with its removal, restore it:

  ```bash
  git mv trash2review/<original/path> <original/path>
  git commit -m "chore: restore <path>"
  ```

- If you agree it's dead, just `git rm -r trash2review/` once you're satisfied.

Each file's removal reason is logged in `.pipeline/purge-plan.md`.
