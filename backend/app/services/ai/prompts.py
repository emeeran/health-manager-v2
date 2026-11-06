"""Runtime prompt loader.

Prompts live at the repo root `prompts/` in dev; the frozen desktop build
bundles them as `sys._MEIPASS/prompts` (Phase 6). load_prompt resolves
upward from this file so both layouts work.
"""

from functools import lru_cache
from pathlib import Path

_APP_SERVICES_AI_DIR = Path(__file__).resolve().parent
_CANDIDATE_ROOTS = [
    # dev: backend/app/services/ai → repo root (4 up)
    _APP_SERVICES_AI_DIR.parents[3],
    # frozen (Phase 6): sys._MEIPASS
    Path(getattr(__import__("sys"), "_MEIPASS", "/nonexistent")),
]


@lru_cache
def load_prompt(name: str) -> str:
    for root in _CANDIDATE_ROOTS:
        path = root / "prompts" / name
        if path.is_file():
            return path.read_text()
    raise FileNotFoundError(f"Prompt template not found: prompts/{name}")
