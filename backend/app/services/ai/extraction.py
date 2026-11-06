"""Document → structured extraction pipeline.

Text PDFs take the text path (PyMuPDF, chunked pages); scans and images
take the vision path (page images rendered at a bounded long side). Every
LLM response is JSON-repaired before parsing — models occasionally emit
prose around the JSON no matter what the prompt says.
"""

import asyncio
import io
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import fitz
import json_repair
from PIL import Image

from app.core.config import get_settings
from app.services.ai.base import ExtractionResult
from app.services.ai.prompts import load_prompt

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
        "medications": [],
        "labs": [],
        "vitals": [],
    }
    for result in results:
        for key in ("medications", "labs", "vitals"):
            merged[key].extend(result.get(key) or [])
        for key in ("record_date", "doctor_name", "facility", "diagnosis", "summary"):
            if result.get(key) and not merged[key]:
                merged[key] = result[key]
    return merged


def parse_llm_json(raw: str) -> dict[str, Any]:
    """Parse model output into a dict, defensively.

    Thinking models (qwen3 etc.) intermittently wrap the JSON in
    <think>…</think> or prose — strip to the outermost {...} before
    repair so a chatty preamble can't reduce the result to {}.
    """
    import re

    cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end > start:
        cleaned = cleaned[start : end + 1]
    parsed: Any = json_repair.loads(cleaned)
    return parsed if isinstance(parsed, dict) else {}


async def _complete_chunk(provider, chunk: PageChunk, progress: Callable) -> dict:
    template = load_prompt("extraction.md")
    if chunk.text is not None:
        content = template.replace("{content}", chunk.text)
        raw = await provider.complete(content, max_tokens=4000)
    else:
        content = template.replace(
            "{content}",
            "(The document pages are attached as images. Read them carefully.)",
        )
        raw = await provider.complete(content, images=chunk.images, max_tokens=4000)
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
