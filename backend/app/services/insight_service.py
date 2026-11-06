"""Shared insight infrastructure: writing style, schemas, grounding.

Three invariants live here and are shared by every AI insight surface
(reports, standalone insights):

1. **CLINICAL_WRITING_STYLE** — one prompt block that every insight prompt
   composes, so the model cannot invent diagnoses, values, or indications.
2. **Pydantic-rendered JSON schemas** — prompts embed a rendering of the
   output Pydantic model (:func:`render_schema_block`) so the prompt and the
   parser can never drift apart (the model returns a structured payload).
3. **"The model narrates, never invents numbers"** — every statistic, count,
   and lab value is computed in code (see ``report_service`` snapshot
   builders) and passed to the model as ground-truth context; the narrative
   references those numbers and must not recompute them.

CMDT-style grounding invariant: reference excerpts come from the
household's OWN indexed PDF (FTS5, see ``app.services.rag``). When RAG
grounds an insight, the citations persisted/returned to the client carry
METADATA ONLY (source filename, page, record id) — excerpt text never
leaves the server. :func:`metadata_only_citations` enforces this at the
boundary; every RAG consumer in the insight family routes citations
through it.
"""

import logging
from typing import Any, Literal, get_args, get_origin

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ── 1. Shared clinical writing standard ──────────────────────────────────────
# Single source of truth for clinical writing discipline, composed into every
# insight prompt (reports + standalone insights).

TONE_DIRECTIVE = (
    "TONE & BREVITY:\n"
    "- Professional and concise: lead with the finding, not the process.\n"
    "- No filler, no restating the question, no meta-commentary about the "
    "data or this task.\n"
    "- Keep every section as short as its content allows; prefer short "
    "declarative sentences.\n"
    "- Cut hedges and throat-clearing ('it is worth noting that', 'may "
    "possibly'); state the finding and its evidence directly.\n"
    "- Each fact appears once — never repeat a data point across sections "
    "or restate the summary at the end.\n"
    "- End after the last substantive point: no closing summary, no "
    "pleasantries, no offer of further help.\n"
)

CLINICAL_WRITING_STYLE = (
    "WRITING STYLE:\n"
    "- Plain, calm language a family can act on; clinical terms are allowed "
    "but explained on first use.\n"
    "- Every claim must cite its evidence inline: the value (with unit), the "
    "date, or the record it came from — all from the GROUND TRUTH data given "
    "to you.\n"
    "- Do NOT invent diagnoses, values, dates, or medication indications. If "
    "the data does not state something, write 'not recorded in the data' "
    "rather than speculating.\n"
    "- Medication names verbatim, exactly as they appear in the data — never "
    "abbreviate or paraphrase a drug name.\n"
    "- When comparing values across time, state both dates and both values.\n"
    "- Never mix data between family members; never recommend anything "
    "beyond discussing the flagged findings with a professional. Red flags "
    "always route to a doctor, never to self-treatment.\n"
) + TONE_DIRECTIVE

CITATION_CONVENTION = (
    "EVIDENCE CITATION — every clinical claim references the specific data "
    "it rests on: the test name, value and date for labs; the medication "
    "name and dose for prescriptions; the vital type, value and date for "
    "readings. If a claim has no data behind it, it must not be made.\n"
)

JSON_HARD_RULES = (
    "RESPONSE FORMAT — CRITICAL:\n"
    "- Respond with ONE valid JSON object and NOTHING else: no markdown, no "
    "code fences, no prose before or after.\n"
    "- Include every schema key; use null (or [] for arrays) when there is "
    "no data — never omit keys.\n"
    "- Copy dates, values and names verbatim from the context.\n"
)


# ── 2. Pydantic-rendered JSON schemas in prompts ─────────────────────────────


def _type_name(t: Any) -> str:
    if get_origin(t) is Literal:
        return " | ".join(str(v) for v in get_args(t))
    return {str: "string", int: "integer", float: "number", bool: "boolean"}.get(
        t, getattr(t, "__name__", str(t))
    )


def _field_type(field: Any) -> str:
    ann = field.annotation
    origin = get_origin(ann)
    if origin is None:
        return _type_name(ann)
    args = get_args(ann)
    if origin is Literal:
        return _type_name(ann)
    inner = " | ".join(_type_name(a) for a in args if a is not type(None))
    if origin is list:
        elem = args[0] if args else Any
        return f"array<{getattr(elem, '__name__', _type_name(elem) if isinstance(elem, type) else 'any')}>"
    if origin is dict:
        return "object"
    return inner or "any"


def render_schema_block(model: type[BaseModel], *, title: str | None = None) -> str:
    """Render a Pydantic model as a compact schema block for a prompt.

    The same model validates the response, so prompt and parser cannot
    drift. Nested BaseModels are inlined one level deep.
    """
    seen: set[type] = {model}

    def lines(m: type[BaseModel]) -> list[str]:
        out: list[str] = []
        for name, field in m.model_fields.items():
            ann = field.annotation
            origin = get_origin(ann)
            args = get_args(ann)
            nested = None
            wrapper = ""
            if (
                origin is list
                and args
                and isinstance(args[0], type)
                and issubclass(args[0], BaseModel)
            ):
                nested, wrapper = args[0], "array of objects"
            elif isinstance(ann, type) and issubclass(ann, BaseModel):
                nested, wrapper = ann, "object"
            if nested is not None and nested not in seen:
                seen.add(nested)
                inner = "; ".join(f"{n}: {_field_type(f)}" for n, f in nested.model_fields.items())
                out.append(f'  "{name}": {wrapper} [{inner}]')
                continue
            t = _field_type(field)
            desc = (field.description or "").strip()
            out.append(f'  "{name}" ({t}) — {desc}' if desc else f'  "{name}" ({t})')
        return out

    header = title or (model.__doc__ or model.__name__).strip().split("\n")[0]
    return f"{header}\n{{\n" + "\n".join(lines(model)) + "\n}"


class InsightAnswer(BaseModel):
    """Structured payload for question-driven standalone insights."""

    headline: str = Field(description="One-sentence direct answer")
    narrative: str = Field(description="Plain-language explanation grounded in the data")
    key_findings: list[str] = Field(
        default_factory=list,
        description="Specific findings cited with value + date, most relevant first",
    )
    recommendations: list[str] = Field(
        default_factory=list,
        description="Actions to discuss with a doctor, grounded in the cited data",
    )


INSIGHT_ANSWER_SCHEMA_TITLE = "HEALTH INSIGHT ANSWER SCHEMA"


# ── 3. CMDT-style grounding invariant (metadata-only citations) ──────────────

GROUNDING_INVARIANT = (
    "Grounding citations returned to the client carry METADATA ONLY: the "
    "reference source filename, the page number, and (when applicable) the "
    "record id. Excerpt text from the indexed reference never leaves the "
    "server — it is prompt-only context."
)

# Keys a serialized citation may carry. Anything else (excerpt text,
# snippets) is stripped — never merged back in.
_ALLOWED_CITATION_KEYS = frozenset({"source", "page", "record_id", "filename"})


def metadata_only_citations(citations: list[dict]) -> list[dict]:
    """Enforce GROUNDING_INVARIANT at the serialization boundary.

    Keeps only metadata keys; excerpt-bearing keys ("text", "snippet", …)
    are dropped so reference prose never leaves the server.
    """
    out: list[dict] = []
    for citation in citations or []:
        metadata = {k: v for k, v in citation.items() if k in _ALLOWED_CITATION_KEYS}
        if metadata:
            out.append(metadata)
    return out


def grounded_reference_block(query: str) -> tuple[str, list[dict]]:
    """Prompt block + metadata-only citations from the local reference index.

    Wraps ``rag.grounding_block``: the excerpt text goes into the prompt
    (where it stays), and the citation list returned to callers is reduced
    to metadata per GROUNDING_INVARIANT. Inert — ("", []) — when the
    household has no reference index built.
    """
    from app.services import rag

    block, citations = rag.grounding_block(query)
    return block, metadata_only_citations(citations)
