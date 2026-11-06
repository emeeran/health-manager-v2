"""SearXNG fact-check tool with deterministic PHI redaction.

Used only by the audit agent, only when the member opted in. The query is
built from generic clinical terms; names, dates and identifiers are
stripped in code before any request leaves the box. Search results are
evidence for the model, never instructions, and result URLs are never
fetched — they are displayed as links only.
"""

import html
import re
from urllib.parse import urlsplit, urlunsplit

import httpx
from pydantic import BaseModel

from app.core.config import get_settings

MAX_QUERY_CHARS = 200
MAX_TITLE_CHARS = 200
MAX_SNIPPET_CHARS = 500
MAX_RESULTS = 8

_IDENTIFIER_PATTERNS = (
    re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I),
    re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    re.compile(r"\+?\d[\d\s().-]{7,}\d"),
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b"),
    re.compile(
        r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}\b",
        re.I,
    ),
    re.compile(r"\b\d+\s*(?:year|yr)s?\s*old\b", re.I),
)

_TAG_RE = re.compile(r"<[^>]+>")
_ALLOWED_CHARS_RE = re.compile(r"[^A-Za-z0-9%./+\-\s]")
_WHITESPACE_RE = re.compile(r"\s+")


class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str = ""


def _clean_text(value: object, *, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    text = html.unescape(_TAG_RE.sub(" ", value))
    return _WHITESPACE_RE.sub(" ", text).strip()[:limit]


def sanitize_url(value: object) -> str | None:
    """http(s) only, no credentials, bounded length, fragment removed."""
    if not isinstance(value, str) or len(value) > 2000:
        return None
    try:
        parts = urlsplit(value.strip())
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    if parts.username or parts.password:
        return None
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))


def redact_query(text: object, names: list[str]) -> str | None:
    """Strip identifiers and household names; return None if unsafe.

    The query is allowed to carry clinical values (``HbA1c 8.4 %``) but not
    a person, a date, a contact detail, or anything that looks like an id.
    """
    if not isinstance(text, str):
        return None

    cleaned = text
    for pattern in _IDENTIFIER_PATTERNS:
        cleaned = pattern.sub(" ", cleaned)

    # Full names first, then individual name tokens (a surname alone is
    # identifying). Longest first so "Mary Ann" is removed before "Mary".
    tokens: set[str] = set()
    for name in names:
        name = (name or "").strip()
        if not name:
            continue
        tokens.add(name)
        tokens.update(part for part in re.split(r"[\s'-]+", name) if len(part) >= 3)
    for token in sorted(tokens, key=len, reverse=True):
        cleaned = re.sub(
            rf"(?<!\w){re.escape(token)}(?!\w)", " ", cleaned, flags=re.IGNORECASE
        )

    cleaned = _ALLOWED_CHARS_RE.sub(" ", cleaned)
    cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip(" ./-")
    cleaned = cleaned[:MAX_QUERY_CHARS].strip()

    if len(cleaned.split()) < 2 or not re.search(r"[A-Za-z]{2,}", cleaned):
        return None
    # Belt and braces: nothing identifier-shaped survived the scrub.
    if any(pattern.search(cleaned) for pattern in _IDENTIFIER_PATTERNS):
        return None
    lowered = cleaned.lower()
    for token in tokens:
        if re.search(rf"(?<!\w){re.escape(token.lower())}(?!\w)", lowered):
            return None
    return cleaned


def available() -> bool:
    settings = get_settings()
    return bool(settings.WEB_FACTCHECK_ENABLED and settings.SEARXNG_URL)


def web_allowed(member) -> bool:
    """Instance capability + the member's explicit opt-in."""
    return bool(available() and member is not None and member.web_factcheck_consent)


async def search(query: str, *, limit: int | None = None) -> list[SearchResult]:
    """Query the configured SearXNG instance; failures degrade to []."""
    settings = get_settings()
    if not available():
        return []
    cap = max(1, min(limit or settings.WEB_FACTCHECK_MAX_RESULTS, MAX_RESULTS))
    base = settings.SEARXNG_URL.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=settings.SEARXNG_TIMEOUT) as client:
            response = await client.get(
                f"{base}/search",
                params={
                    "q": query,
                    "format": "json",
                    "categories": "general",
                    "language": "en",
                    "safesearch": 1,
                },
                headers={"User-Agent": "FamilyHealthManager/1.0 (+self-hosted fact-check)"},
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError):
        return []

    results: list[SearchResult] = []
    seen: set[str] = set()
    for item in payload.get("results", []) if isinstance(payload, dict) else []:
        if not isinstance(item, dict):
            continue
        url = sanitize_url(item.get("url"))
        title = _clean_text(item.get("title"), limit=MAX_TITLE_CHARS)
        if not url or not title:
            continue
        key = url.lower()
        if key in seen:
            continue
        seen.add(key)
        results.append(
            SearchResult(
                title=title,
                url=url,
                snippet=_clean_text(item.get("content"), limit=MAX_SNIPPET_CHARS),
            )
        )
        if len(results) >= cap:
            break
    return results
