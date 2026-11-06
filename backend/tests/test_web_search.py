"""Web fact-check tool: redaction, URL sanitization, SearXNG parsing."""

import httpx
import pytest

from app.core.config import get_settings
from app.services.ai import web_search

_ORIGINAL_CLIENT_INIT = httpx.AsyncClient.__init__


def _mock_transport(monkeypatch, handler) -> list[httpx.Request]:
    seen: list[httpx.Request] = []

    def patched_init(self, *args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(
            lambda request: (seen.append(request), handler(request))[1]
        )
        _ORIGINAL_CLIENT_INIT(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)
    return seen


def _enable(monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "WEB_FACTCHECK_ENABLED", True)
    monkeypatch.setattr(settings, "SEARXNG_URL", "http://searx.local")


def test_redact_strips_names_dates_and_identifiers():
    query = web_search.redact_query(
        "HbA1c 8.4 % on 2026-05-01 for John Smith, john@example.com",
        ["John Smith"],
    )
    assert query is not None
    assert "8.4" in query
    assert "HbA1c" in query
    for forbidden in ("John", "Smith", "2026", "example.com"):
        assert forbidden not in query


def test_redact_rejects_a_query_that_is_only_an_identity():
    assert web_search.redact_query("John Smith", ["John Smith"]) is None
    assert web_search.redact_query("2026-05-01 919191919191", ["John Smith"]) is None
    assert web_search.redact_query("", ["John Smith"]) is None


def test_redact_removes_uuids_and_phones():
    query = web_search.redact_query(
        "interaction 3f2504e0-4f89-11d3-9a0c-0305e82c3301 +91 98765 43210 warfarin",
        [],
    )
    assert query is not None
    assert "warfarin" in query
    assert "3f2504e0" not in query
    assert "98765" not in query


def test_sanitize_url_allows_only_http_and_https():
    assert web_search.sanitize_url("https://example.org/a#frag") == "https://example.org/a"
    assert web_search.sanitize_url("https://user:pass@example.org/a") is None
    assert web_search.sanitize_url("javascript:alert(1)") is None
    assert web_search.sanitize_url("file:///etc/passwd") is None
    assert web_search.sanitize_url("not a url") is None


@pytest.mark.asyncio
async def test_search_parses_and_dedupes_results(monkeypatch):
    _enable(monkeypatch)
    payload = {
        "results": [
            {
                "title": "<b>Statin</b> guidance",
                "url": "https://example.org/statin#section",
                "content": "<p>Target LDL &lt; 100</p>",
            },
            {
                "title": "Duplicate",
                "url": "https://example.org/statin",
                "content": "dup",
            },
            {"title": "Bad", "url": "javascript:alert(1)", "content": "x"},
        ]
    }
    _mock_transport(monkeypatch, lambda request: httpx.Response(200, json=payload))

    results = await web_search.search("statin target", limit=5)

    assert len(results) == 1
    assert results[0].title == "Statin guidance"
    assert results[0].snippet == "Target LDL < 100"
    assert results[0].url == "https://example.org/statin"


@pytest.mark.asyncio
async def test_search_returns_empty_on_failure(monkeypatch):
    _enable(monkeypatch)

    def boom(request):
        raise httpx.ConnectError("down", request=request)

    _mock_transport(monkeypatch, boom)

    assert await web_search.search("statin target") == []


def test_web_requires_capability_and_consent(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "WEB_FACTCHECK_ENABLED", False)
    monkeypatch.setattr(settings, "SEARXNG_URL", "http://searx.local")

    class Member:
        web_factcheck_consent = True

    assert web_search.web_allowed(Member()) is False

    monkeypatch.setattr(settings, "WEB_FACTCHECK_ENABLED", True)
    assert web_search.web_allowed(Member()) is True
    Member.web_factcheck_consent = False
    assert web_search.web_allowed(Member()) is False
