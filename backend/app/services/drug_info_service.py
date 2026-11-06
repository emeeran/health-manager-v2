"""Drug-information lookups: openFDA → RxNorm → AI generic fallback.

Resolves a free-text medicine name to {brand, generic, manufacturer,
ingredients, source}. openFDA matches best on brand/generic names; when it has
no entry the name is normalized via RxNorm (NIH); when both registries miss,
the configured AI provider is asked for the single active ingredient.

Every external HTTP call goes through a small module-level function
(``_openfda_get`` / ``_rxnorm_get``) so tests can monkeypatch it — no test ever
touches the network. All lookups degrade to nulls on failure, never raise.
"""

from __future__ import annotations

import logging
import os
import re
import time

import httpx

logger = logging.getLogger(__name__)

OPENFDA_BASE_URL = "https://api.fda.gov"
RXNORM_BASE_URL = "https://rxnav.nlm.nih.gov/REST"
_OPENFDA_TIMEOUT = 10.0
_RXNORM_TIMEOUT = 10.0
# NLM silently returns empty bodies for bare/curl User-Agents.
_USER_AGENT = "FamilyHealthManager/2.0 (self-hosted family health record)"


async def _http_get_json(url: str, params: dict, *, label: str, timeout: float) -> dict | None:
    """Shared GET helper — parsed JSON object or None on any failure."""
    try:
        async with httpx.AsyncClient(
            timeout=timeout, headers={"User-Agent": _USER_AGENT}
        ) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            payload: object = resp.json()
            return payload if isinstance(payload, dict) else None
    except Exception:  # noqa: BLE001 — degrade to "no data", never raise
        logger.debug("%s GET failed: %s", label, url, exc_info=True)
        return None


async def _openfda_get(url: str, params: dict) -> dict | None:
    """GET an openFDA endpoint, returning parsed JSON or None on any failure.

    Module-level precisely so tests monkeypatch it. openFDA answers 404 (no
    matches) for missing drugs — that is "no data", not an error.
    """
    return await _http_get_json(url, params, label="openFDA", timeout=_OPENFDA_TIMEOUT)


async def _rxnorm_get(path: str, params: dict | None = None) -> dict | None:
    """GET an RxNorm REST path (appended to RXNORM_BASE_URL), or None on failure."""
    return await _http_get_json(
        f"{RXNORM_BASE_URL}/{path}", params or {}, label="RxNorm", timeout=_RXNORM_TIMEOUT
    )


def _api_key() -> str:
    """Optional openFDA key — env-configured (raises no-key rate limits)."""
    return os.environ.get("OPENFDA_API_KEY", "")


def _quoted(term: str) -> str:
    """openFDA phrase: wrap in double quotes so multi-word terms stay one token."""
    return '"' + term.replace('"', "") + '"'


def _first(value: object) -> str | None:
    """openFDA list fields → first element, else None."""
    if isinstance(value, list) and value:
        return str(value[0])
    if isinstance(value, str) and value:
        return value
    return None


# ── openFDA ──────────────────────────────────────────────────────────


async def openfda_drug_info(name: str) -> dict | None:
    """Best-match openFDA label entry for ``name``, shaped, or None."""
    params: dict = {
        "search": (f"openfda.generic_name:{_quoted(name)} OR openfda.brand_name:{_quoted(name)}"),
        "limit": 1,
    }
    key = _api_key()
    if key:
        params["api_key"] = key
    body = await _openfda_get(f"{OPENFDA_BASE_URL}/drug/label.json", params)
    results = body.get("results") if isinstance(body, dict) else None
    if not isinstance(results, list) or not results:
        return None
    row = results[0]
    if not isinstance(row, dict):
        return None
    meta_raw = row.get("openfda")
    meta: dict = meta_raw if isinstance(meta_raw, dict) else {}
    active = row.get("active_ingredient")
    if isinstance(active, list):
        ingredients = "; ".join(str(a) for a in active if a)
    elif isinstance(active, str):
        ingredients = active
    else:
        ingredients = ""
    return {
        "brand": _first(meta.get("brand_name")),
        "generic": _first(meta.get("generic_name")),
        "manufacturer": _first(meta.get("manufacturer_name")),
        "ingredients": ingredients or None,
        "source": "openfda",
    }


# ── RxNorm ───────────────────────────────────────────────────────────


async def rxnorm_resolve(name: str) -> dict | None:
    """Free-text name → ``{rxcui, name, tty}`` via RxNorm, or None.

    Two-step: approximateTerm (fuzzy) gives a candidate RXCUI, properties
    returns the canonical name. When the candidate is a brand/clinical drug,
    the active ingredient (IN) is resolved so "Glucophage" → "metformin".
    """
    if not name or not name.strip():
        return None
    body = await _rxnorm_get("approximateTerm.json", {"term": name.strip(), "maxEntries": 1})
    rxcui = _first_rxcui(body)
    if not rxcui:
        return None
    props_body = await _rxnorm_get(f"rxcui/{rxcui}/properties.json")
    props = props_body.get("properties") if isinstance(props_body, dict) else None
    if not isinstance(props, dict) or not props.get("name"):
        return None
    tty = props.get("tty") or ""
    resolved_name = str(props["name"])
    if tty and tty not in ("IN", "PIN", "MIN"):
        ingredient = await _ingredient_of(rxcui)
        if ingredient:
            return {"rxcui": str(rxcui), "name": ingredient, "tty": "IN"}
    return {"rxcui": str(rxcui), "name": resolved_name, "tty": tty}


async def _ingredient_of(rxcui: str) -> str | None:
    """Active-ingredient (IN) name for a brand/clinical-drug RXCUI, or None."""
    body = await _rxnorm_get(f"rxcui/{rxcui}/related.json", {"tty": "IN"})
    if not isinstance(body, dict):
        return None
    groups = body.get("relatedGroup", {}).get("conceptGroup", [])
    if not isinstance(groups, list):
        return None
    for group in groups:
        if not isinstance(group, dict):
            continue
        for concept in group.get("conceptProperties") or []:
            if isinstance(concept, dict) and concept.get("tty") == "IN" and concept.get("name"):
                return str(concept["name"])
    return None


def _first_rxcui(body: object) -> str | None:
    """Top candidate RXCUI from an approximateTerm response."""
    if not isinstance(body, dict):
        return None
    group = body.get("approximateGroup")
    if not isinstance(group, dict):
        return None
    candidates = group.get("candidate")
    if not isinstance(candidates, list) or not candidates:
        return None
    first = candidates[0]
    if isinstance(first, dict) and first.get("rxcui"):
        return str(first["rxcui"])
    return None


# ── AI generic-name fallback ─────────────────────────────────────────

_GENERIC_RE = re.compile(r"[A-Za-z][A-Za-z\-]*")
_NON_ANSWERS = {"unknown", "none", "na", "n", "no", "not", "unsure", "null"}


def sanitize_generic(raw: str) -> str | None:
    """Pull one plausible generic token out of an AI reply, or None."""
    match = _GENERIC_RE.search(raw or "")
    if not match:
        return None
    token = match.group(0).lower()
    if token in _NON_ANSWERS or not 3 <= len(token) <= 40:
        return None
    return token


async def ai_generic_name(name: str, local_only: bool = False) -> str | None:
    """Ask the configured AI for the active ingredient of ``name``.

    Uses the provider failover chain (local-only when the member withheld
    cloud consent). Returns a sanitized single token, or None when no
    provider is available or it is unsure.
    """
    from app.services.ai import router as ai_router

    provider = await ai_router.first_available(ai_router.build_plan(local_only=local_only))
    if provider is None:
        return None
    prompt = (
        "You map medicine names to their single generic active ingredient. "
        f'Medicine: "{name}". '
        "Reply with ONLY the lowercase generic (active ingredient) name and "
        "nothing else — no punctuation, no explanation. If you are not "
        "confident, reply exactly: unknown"
    )
    try:
        reply = await provider.complete(prompt)
    except Exception:  # noqa: BLE001 — never let an AI failure break a lookup
        logger.debug("AI generic fallback failed for %r", name, exc_info=True)
        return None
    return sanitize_generic(reply or "")


# ── orchestration + light in-process cache ───────────────────────────

_CACHE_TTL_SECONDS = 24 * 3600
_cache: dict[str, tuple[dict, float]] = {}


def _cache_key(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


def _cache_get(key: str, now: float) -> dict | None:
    hit = _cache.get(key)
    if hit and now - hit[1] < _CACHE_TTL_SECONDS:
        return hit[0]
    if hit:
        _cache.pop(key, None)
    return None


async def lookup_drug(medicine: str, local_only: bool = False) -> dict:
    """Resolve ``medicine`` → {brand, generic, manufacturer, ingredients, source}.

    Resolution order: openFDA (authoritative label data) → RxNorm (generic
    name) → AI (generic guess). Results are cached in-process for 24h
    (registry content is stable; flyouts re-open often). Never raises.
    """
    if not medicine or not medicine.strip():
        return _empty()
    key = _cache_key(medicine)
    now = time.monotonic()
    cached = _cache_get(key, now)
    if cached is not None:
        return dict(cached)

    result = await _resolve(medicine, local_only)
    _cache[key] = (result, now)
    return dict(result)


async def _resolve(medicine: str, local_only: bool) -> dict:
    name = medicine.strip()
    info = await openfda_drug_info(name)
    if info:
        return info

    resolved = await rxnorm_resolve(name)
    if resolved and resolved.get("name"):
        return {
            "brand": None,
            "generic": resolved["name"],
            "manufacturer": None,
            "ingredients": None,
            "source": "rxnorm",
        }

    generic = await ai_generic_name(name, local_only=local_only)
    if generic:
        return {
            "brand": None,
            "generic": generic,
            "manufacturer": None,
            "ingredients": None,
            "source": "ai",
        }
    return _empty()


def _empty() -> dict:
    return {
        "brand": None,
        "generic": None,
        "manufacturer": None,
        "ingredients": None,
        "source": "unavailable",
    }


def clear_cache() -> None:
    """Test/diagnostic helper — drop the in-process cache."""
    _cache.clear()
