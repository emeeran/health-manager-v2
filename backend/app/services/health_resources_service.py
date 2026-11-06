"""Health-resources lookups: MedlinePlus Connect / DailyMed / Health Canada / MHRA.

Patient-education and official-label metadata for a search term. Every provider
returns metadata only (title / url / summary) — page bodies are never proxied;
the client opens the source link directly.

All external HTTP goes through module-level callables (``_medlineplus_get``,
``_dailymed_get``, ``_hcdpd_get``, ``_mhra_get``) so tests monkeypatch them.
Every lookup degrades to an empty list on failure — never raises.
"""

from __future__ import annotations

import logging
import re

import httpx

from app.services import drug_info_service

logger = logging.getLogger(__name__)

_TIMEOUT = 10.0
_USER_AGENT = drug_info_service._USER_AGENT

_MEDLINEPLUS_CONNECT_URL = "https://connect.medlineplus.gov/service"
_DAILYMED_BASE_URL = "https://dailymed.nlm.nih.gov/dailymed/services/v2"
_HEALTH_CANADA_DPD_URL = "https://health-products.canada.ca/api/drug"
_GOV_UK_SEARCH_URL = "https://www.gov.uk/api/search"

# GOV.UK content-store organisation slug for the MHRA.
_MHRA_ORG = "medicines-and-healthcare-products-regulatory-agency"

# MedlinePlus Connect code-system OID for RxNorm (drugs, by RXCUI).
_RXNORM_OID = "2.16.840.1.113883.6.88"

_DIN_RE = re.compile(r"^\d{8}$")


async def _http_get_json(url: str, params: dict) -> dict | list | None:
    """Shared GET helper — parsed JSON or None on any failure (never raises)."""
    try:
        async with httpx.AsyncClient(
            timeout=_TIMEOUT, headers={"User-Agent": _USER_AGENT}
        ) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            payload: object = resp.json()
            return payload if isinstance(payload, (dict, list)) else None
    except Exception:  # noqa: BLE001 — degrade to "no data"
        logger.debug("health-resources GET failed: %s", url, exc_info=True)
        return None


async def _medlineplus_get(url: str, params: dict) -> dict | None:
    result = await _http_get_json(url, params)
    return result if isinstance(result, dict) else None


async def _dailymed_get(url: str, params: dict) -> dict | None:
    result = await _http_get_json(url, params)
    return result if isinstance(result, dict) else None


async def _hcdpd_get(url: str, params: dict) -> list | None:
    result = await _http_get_json(url, params)
    return result if isinstance(result, list) else None


async def _mhra_get(url: str, params: dict) -> dict | None:
    result = await _http_get_json(url, params)
    return result if isinstance(result, dict) else None


# ── providers ────────────────────────────────────────────────────────


async def medlineplus_for_term(term: str) -> list[dict]:
    """Patient-education topics for a drug term → [{title, url, summary}].

    MedlinePlus Connect matches on an RXCUI, so the term is resolved via
    RxNorm first; terms that don't resolve to a code yield no topics.
    """
    if not term or not term.strip():
        return []
    resolved = await drug_info_service.rxnorm_resolve(term)
    rxcui = (resolved or {}).get("rxcui")
    if not rxcui:
        return []
    body = await _medlineplus_get(
        _MEDLINEPLUS_CONNECT_URL,
        {
            "mainSearchCriteria.v.cs": _RXNORM_OID,
            "mainSearchCriteria.v.c": str(rxcui),
            "knowledgeResponseType": "application/json",
        },
    )
    if not isinstance(body, dict):
        return []
    out: list[dict] = []
    for entry in body.get("entry") or []:
        if not isinstance(entry, dict):
            continue
        links = entry.get("link") or []
        url = links[0].get("href") if links and isinstance(links[0], dict) else None
        if not url:
            continue
        title = entry.get("title")
        if isinstance(title, dict):  # {"_value": "..."} form
            title = title.get("_value")
        out.append(
            {
                "title": str(title or ""),
                "url": str(url),
                "summary": str(entry.get("summary") or ""),
            }
        )
    return out


async def dailymed_for_term(term: str, limit: int = 3) -> list[dict]:
    """Full-label (SPL) links for a drug name → [{title, setid, url, summary}]."""
    if not term or not term.strip():
        return []
    body = await _dailymed_get(
        f"{_DAILYMED_BASE_URL}/spls.json",
        {"drug_name": term.strip(), "pagesize": str(max(1, min(limit, 10)))},
    )
    if not isinstance(body, dict):
        return []
    out: list[dict] = []
    for item in body.get("data") or []:
        if not isinstance(item, dict):
            continue
        setid = item.get("setid")
        if not setid:
            continue
        out.append(
            {
                "title": item.get("title") or "",
                "setid": str(setid),
                "url": f"https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={setid}",
                "summary": "",
            }
        )
    return out


async def hcdpd_for_term(term: str) -> list[dict]:
    """Health Canada DPD product metadata for a term → [{title, url, summary}].

    The DPD API only supports exact DIN lookup cleanly; an 8-digit term is
    treated as a DIN, anything else as a brand-name query.
    """
    term = (term or "").strip()
    if not term:
        return []
    if _DIN_RE.match(term):
        params: dict = {"din": term, "lang": "en", "type": "json"}
    else:
        params = {"brand_name": term, "lang": "en", "type": "json"}
    rows = await _hcdpd_get(f"{_HEALTH_CANADA_DPD_URL}/drugproduct/", params)
    if not isinstance(rows, list):
        return []
    out: list[dict] = []
    for row in rows[:5]:
        if not isinstance(row, dict) or not row.get("drug_identification_number"):
            continue
        drug_code = row.get("drug_code")
        out.append(
            {
                "title": row.get("brand_name") or "",
                "url": (
                    f"https://health-products.canada.ca/dpd-bdpp/info.do?lang=en&code={drug_code}"
                    if drug_code
                    else "https://health-products.canada.ca/dpd-bdpp/"
                ),
                "summary": " ".join(
                    part
                    for part in [
                        row.get("company_name"),
                        row.get("descriptor"),
                        f"DIN {row['drug_identification_number']}",
                    ]
                    if part
                ),
            }
        )
    return out


async def mhra_for_term(term: str, limit: int = 5) -> list[dict]:
    """MHRA drug-safety entries (GOV.UK search API) → [{title, url, summary}]."""
    if not term or not term.strip():
        return []
    body = await _mhra_get(
        _GOV_UK_SEARCH_URL,
        {
            "q": term.strip(),
            "filter_organisations": _MHRA_ORG,
            "count": str(max(1, min(limit, 20))),
        },
    )
    if not isinstance(body, dict):
        return []
    out: list[dict] = []
    for row in body.get("results") or []:
        if not isinstance(row, dict):
            continue
        link = row.get("link")
        if not link:
            continue
        url = link if str(link).startswith("http") else f"https://www.gov.uk{link}"
        out.append(
            {
                "title": row.get("title") or "",
                "url": url,
                "summary": (row.get("description") or "").strip(),
            }
        )
    return out


SOURCES = {
    "medlineplus": medlineplus_for_term,
    "dailymed": dailymed_for_term,
    "hc-dpd": hcdpd_for_term,
    "mhra": mhra_for_term,
}


async def lookup(term: str, source: str) -> list[dict]:
    """Dispatch a metadata lookup to the named source. Never raises."""
    provider = SOURCES.get(source)
    if provider is None:
        return []
    try:
        return await provider(term)
    except Exception:  # noqa: BLE001 — a blank panel beats a 500
        logger.warning("health-resources lookup failed (%s %r)", source, term, exc_info=True)
        return []
