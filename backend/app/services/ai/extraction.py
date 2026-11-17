"""Document → structured extraction pipeline.

Text PDFs take the text path (PyMuPDF, chunked pages); scans and images
take the vision path (page images rendered at a bounded long side). Every
LLM response is JSON-repaired before parsing — models occasionally emit
prose around the JSON no matter what the prompt says.
"""

import asyncio
import io
import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

import fitz
import json_repair
from PIL import Image

from app.core.config import get_settings
from app.services.ai.base import ExtractionResult
from app.services.ai.prompts import load_prompt

logger = logging.getLogger(__name__)

VISION_MAX_DIM = 1568
MIN_EMBEDDED_TEXT_CHARS = 100

# Module-level callables so tests can patch them (upstream pattern).
call_provider = None  # set by run_extraction; patched in tests


@dataclass
class PageChunk:
    pages: list[int]
    text: str | None = None
    images: list[bytes] | None = None


def pdf_page_images(data: bytes, page_numbers: list[int]) -> list[bytes]:
    images = []
    with fitz.open(stream=data, filetype="pdf") as doc:
        for n in page_numbers:
            pix = doc[n].get_pixmap(dpi=120)
            page_img: Image.Image = Image.open(io.BytesIO(pix.tobytes("png")))
            page_img = page_img.convert("RGB")
            page_img.thumbnail((VISION_MAX_DIM, VISION_MAX_DIM))
            buf = io.BytesIO()
            page_img.save(buf, format="JPEG", quality=80)
            images.append(buf.getvalue())
    return images


def build_chunks(data: bytes, mime: str) -> list[PageChunk]:
    """Text chunks for text PDFs, image chunks for scans/images."""
    per_chunk = get_settings().EXTRACTION_PAGES_PER_CHUNK
    if mime != "application/pdf":
        opened: Image.Image = Image.open(io.BytesIO(data))
        opened = opened.convert("RGB")
        opened.thumbnail((VISION_MAX_DIM, VISION_MAX_DIM))
        buf = io.BytesIO()
        opened.save(buf, format="JPEG", quality=80)
        return [PageChunk(pages=[0], images=[buf.getvalue()])]

    with fitz.open(stream=data, filetype="pdf") as doc:
        texts = [doc[n].get_text() for n in range(doc.page_count)]
    total_chars = sum(len(t) for t in texts)
    if total_chars >= MIN_EMBEDDED_TEXT_CHARS:
        chunks = []
        for start in range(0, len(texts), per_chunk):
            page_nums = list(range(start, min(start + per_chunk, len(texts))))
            chunks.append(
                PageChunk(
                    pages=page_nums,
                    text="\n\n".join(f"[page {n + 1}]\n{texts[n]}" for n in page_nums),
                )
            )
        return chunks
    # Scanned PDF: vision path over rendered pages.
    chunks = []
    for start in range(0, len(texts), per_chunk):
        page_nums = list(range(start, min(start + per_chunk, len(texts))))
        chunks.append(
            PageChunk(
                pages=page_nums,
                images=pdf_page_images(data, page_nums),
            )
        )
    return chunks


def merge_chunk_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge per-chunk extractions; later chunks never clobber earlier data."""
    merged: dict[str, Any] = {
        "record_date": None,
        "doctor_name": None,
        "facility": None,
        "diagnosis": None,
        "summary": None,
        "patient": None,
        "clinical_history": None,
        "exam_findings": None,
        "encounter_no": None,
        "ward": None,
        "address": None,
        "phone": None,
        "insurance": None,
        "medications": [],
        "imaging": [],
        "screenings": [],
        "labs": [],
        "vitals": [],
    }
    for result in results:
        for key in (
            "medications",
            "imaging",
            "screenings",
            "labs",
            "vitals",
        ):
            merged[key].extend(result.get(key) or [])
        for key in (
            "record_date",
            "doctor_name",
            "facility",
            "diagnosis",
            "summary",
            "patient",
            "clinical_history",
            "exam_findings",
            "encounter_no",
            "ward",
            "address",
            "phone",
            "insurance",
        ):
            if result.get(key) and not merged[key]:
                merged[key] = result[key]
    # A closing summary section often restates items an earlier chunk already
    # extracted verbatim — drop exact repeats, keep distinct dates/values.
    for key, identity in (
        ("medications", lambda m: (str(m.get("name", "")).lower(), str(m.get("dosage")))),
        ("imaging", lambda i: (str(i.get("modality")), str(i.get("region")), str(i.get("date")))),
        ("screenings", lambda s: (str(s.get("type", "")).lower(), str(s.get("date")))),
        ("labs", lambda row: (str(row.get("name", "")).lower(), str(row.get("result")), str(row.get("date")))),
        ("vitals", lambda v: (str(v.get("type")), str(v.get("value")), str(v.get("value_secondary")))),
    ):
        seen: set = set()
        deduped = []
        for item in merged[key]:
            marker = identity(item)
            if marker in seen:
                continue
            seen.add(marker)
            deduped.append(item)
        merged[key] = deduped
    return merged


def parse_llm_json(raw: str) -> dict[str, Any]:
    """Parse model output into a dict, defensively.

    Thinking models (qwen3 etc.) intermittently wrap the JSON in
    <think>…</think> or prose — strip to the outermost {...} before
    repair so a chatty preamble can't reduce the result to {}.
    """
    cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end > start:
        cleaned = cleaned[start : end + 1]
    parsed: Any = json_repair.loads(cleaned)
    return parsed if isinstance(parsed, dict) else {}


async def _complete_chunk(provider, chunk: PageChunk, progress: Callable) -> dict:
    template = load_prompt("extraction.md")
    # EXTRACTION_MAX_TOKENS, not a hardcoded value: reasoning models burn
    # completion budget on thinking before the JSON, so a tight cap truncates
    # the payload mid-list and json_repair salvages only a fragment.
    max_tokens = get_settings().EXTRACTION_MAX_TOKENS
    if chunk.text is not None:
        content = template.replace("{content}", chunk.text)
        raw = await provider.complete(content, max_tokens=max_tokens)
    else:
        content = template.replace(
            "{content}",
            "(The document pages are attached as images. Read them carefully.)",
        )
        raw = await provider.complete(content, images=chunk.images, max_tokens=max_tokens)
    progress("extracting", f"extracted pages {chunk.pages[0] + 1}-{chunk.pages[-1] + 1}")
    return parse_llm_json(raw)


async def run_extraction(
    data: bytes,
    mime: str,
    provider,
    progress: Callable[[str, str], Any] | None = None,
) -> ExtractionResult:
    """Run the full pipeline against one provider.

    `provider` is resolved by the caller (router/first_available or a fake
    in tests) — this function is provider-agnostic.
    """
    progress = progress or (lambda stage, message: None)
    progress("reading", "preparing document")
    chunks = await asyncio.to_thread(build_chunks, data, mime)
    results = []
    for chunk in chunks:
        results.append(await _complete_chunk(provider, chunk, progress))
    clinical = merge_chunk_results([r for r in results if isinstance(r, dict)])
    summary = clinical.get("summary")
    return ExtractionResult(
        clinical_data=clinical,
        summary=str(summary) if summary else None,
        provider_used=provider.name,
    )


def _short_provider_error(exc: Exception) -> str:
    """One compact line per failed provider for the aggregate error — the
    raw httpx message carries a URL and a docs link nobody debugging the
    settings board needs."""
    msg = str(exc).splitlines()[0]
    msg = re.sub(r"\s*For more information.*$", "", msg).strip()
    return msg or type(exc).__name__


async def run_extraction_with_failover(
    data: bytes,
    mime: str,
    plan: list,
    progress: Callable[[str, str], Any] | None = None,
) -> ExtractionResult:
    """Run the pipeline against the plan in order, failing over on errors.

    A provider that raises (400 for an unsupported request shape, 429 rate
    limit, timeout, dead key) is negative-cached via ``mark_unhealthy`` — so
    the next plan resolution skips it for the health TTL — and the next
    provider in the plan is tried. When every provider fails, raises a
    RuntimeError naming each provider's reason — the last error alone
    blames the tail of the plan for a failure rooted earlier in it.
    ``result.provider_used`` reports who actually won.
    """
    from app.services.ai import router as ai_router

    progress = progress or (lambda stage, message: None)
    if not plan:
        raise RuntimeError("No AI provider available")
    failures: list[str] = []
    for provider in plan:
        try:
            return await run_extraction(data, mime, provider, progress)
        except Exception as exc:  # noqa: BLE001 — any provider failure means "try next"
            failures.append(f"{provider.name}: {_short_provider_error(exc)}")
            ai_router.mark_unhealthy(provider.name)
            logger.warning(
                "extraction failed via %s: %s — trying next provider", provider.name, exc
            )
            progress("failover", f"{provider.name} failed — trying next provider")
    raise RuntimeError("all providers failed — " + "; ".join(failures))


def strip_report_markdown(raw: str) -> str:
    """Clean an LLM report reply down to the bare markdown document."""
    cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
    # A fence-wrapped document (```markdown … ```) is common despite the
    # prompt; unwrap the outermost fence instead of rendering the ticks.
    fence = re.match(
        r"^\s*```[^\n]*\n(.*)\n```\s*$", cleaned, flags=re.DOTALL
    )
    if fence:
        cleaned = fence.group(1)
    return cleaned.strip()


async def run_consolidated_report(
    clinical_data: dict[str, Any],
    plan: list,
    progress: Callable[[str, str], Any] | None = None,
) -> str:
    """Second pass: restructure extracted clinical_data into the
    consolidated-report markdown (prompts/consolidated-report.md).

    Runs after a successful extraction and speaks to the same provider
    plan with the same failover semantics. Raises when every provider
    fails — callers treat the report as optional and keep the extraction.
    """
    from app.services.ai import router as ai_router

    progress = progress or (lambda stage, message: None)
    if not plan:
        raise RuntimeError("No AI provider available")
    template = load_prompt("consolidated-report.md")
    content = json.dumps(
        {"report_date": date.today().isoformat(), "clinical_data": clinical_data},
        ensure_ascii=False,
        default=str,
    )
    prompt = template.replace("{report_date}", date.today().isoformat()).replace(
        "{content}", content
    )
    # Providers the extraction already burned (dead keys, 429s) are
    # negative-cached — don't feed the report pass the same losers.
    candidates = await ai_router.available_providers(plan)
    if not candidates:
        raise RuntimeError("No AI provider available")
    last_exc: Exception | None = None
    for provider in candidates:
        try:
            raw = await provider.complete(
                prompt, max_tokens=get_settings().EXTRACTION_MAX_TOKENS
            )
            report = strip_report_markdown(raw)
            if report:
                return report
            raise RuntimeError("model returned an empty report")
        except Exception as exc:  # noqa: BLE001 — any provider failure means "try next"
            last_exc = exc
            ai_router.mark_unhealthy(provider.name)
            logger.warning(
                "consolidated report failed via %s: %s — trying next provider",
                provider.name,
                exc,
            )
    assert last_exc is not None
    raise last_exc
