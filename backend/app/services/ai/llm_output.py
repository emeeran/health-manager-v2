"""Cleaning raw LLM replies into structured data.

Models wrap JSON in <think> blocks, markdown fences, and chatty prose;
every consumer of a JSON reply goes through :func:`parse_llm_json`.
"""

import re
from typing import Any

import json_repair


def strip_think_blocks(raw: str) -> str:
    """Drop thinking-model <think> wrappers and surrounding whitespace."""
    return re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()


def parse_llm_json(raw: str) -> dict[str, Any]:
    """Parse model output into a dict, defensively.

    Thinking models (qwen3 etc.) intermittently wrap the JSON in
    <think>…</think> or prose — strip to the outermost {...} before
    repair so a chatty preamble can't reduce the result to {}.
    """
    cleaned = strip_think_blocks(raw)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end > start:
        cleaned = cleaned[start : end + 1]
    parsed: Any = json_repair.loads(cleaned)
    return parsed if isinstance(parsed, dict) else {}
