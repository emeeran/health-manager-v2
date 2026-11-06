"""Drug-info, health-resources and drug-catalog search (all external HTTP mocked)."""

from typing import Any

import pytest

from app.services import drug_info_service, health_resources_service, local_drug_service
from app.services.ai import router as ai_router


class FakeProvider:
    """AI provider stand-in — no network."""

    def __init__(self, reply: str | None = None, name: str = "fake") -> None:
        self.name = name
        self.model = "fake-model"
        self.local = name.startswith("local")
        self.timeout = 5
        self.reply = reply
        self.calls: list[dict[str, Any]] = []

    async def available(self) -> bool:
        return True

    async def complete(self, prompt: str, **kwargs: Any) -> str:
        self.calls.append({"prompt": prompt, **kwargs})
        return self.reply or ""


@pytest.fixture(autouse=True)
def _clear_caches():
    drug_info_service.clear_cache()
    yield
    drug_info_service.clear_cache()


async def _create_member(client, **kwargs) -> str:
    resp = await client.post("/api/v1/members", json={"name": "Asha", **kwargs})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# ── drug info ────────────────────────────────────────────────────────


async def test_drug_info_openfda_hit(auth_client, monkeypatch):
    member_id = await _create_member(auth_client)
    calls = {"openfda": 0, "rxnorm": 0}

    async def fake_openfda(url, params):
        calls["openfda"] += 1
        assert "api.fda.gov" in url
        assert "openfda.generic_name" in params["search"]
        return {
            "results": [
                {
                    "openfda": {
                        "brand_name": ["Glucophage"],
                        "generic_name": ["Metformin Hydrochloride"],
                        "manufacturer_name": ["Merck Sharp & Dohme"],
                    },
                    "active_ingredient": ["METFORMIN HYDROCHLORIDE 500 MG"],
                }
            ]
        }

    async def fake_rxnorm(path, params=None):
        calls["rxnorm"] += 1
        return None

    monkeypatch.setattr(drug_info_service, "_openfda_get", fake_openfda)
    monkeypatch.setattr(drug_info_service, "_rxnorm_get", fake_rxnorm)

    resp = await auth_client.get(
        f"/api/v1/members/{member_id}/drug-info", params={"medicine": "metformin 500mg"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source"] == "openfda"
    assert body["brand"] == "Glucophage"
    assert body["generic"] == "Metformin Hydrochloride"
    assert body["manufacturer"] == "Merck Sharp & Dohme"
    assert "METFORMIN HYDROCHLORIDE 500 MG" in body["ingredients"]
    assert calls["rxnorm"] == 0, "openFDA hit must short-circuit RxNorm"


async def test_drug_info_rxnorm_fallback_when_openfda_404(auth_client, monkeypatch):
    member_id = await _create_member(auth_client)

    async def fake_openfda(url, params):
        return None  # openFDA 404 — no matches

    async def fake_rxnorm(path, params=None):
        if path.endswith("approximateTerm.json"):
            return {"approximateGroup": {"candidate": [{"rxcui": "6809"}]}}
        assert path.endswith("rxcui/6809/properties.json")
        return {"properties": {"rxcui": "6809", "name": "Metformin", "tty": "IN"}}

    monkeypatch.setattr(drug_info_service, "_openfda_get", fake_openfda)
    monkeypatch.setattr(drug_info_service, "_rxnorm_get", fake_rxnorm)

    resp = await auth_client.get(
        f"/api/v1/members/{member_id}/drug-info", params={"medicine": "glucophage"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source"] == "rxnorm"
    assert body["generic"] == "Metformin"


async def test_drug_info_ai_generic_fallback(auth_client, monkeypatch):
    member_id = await _create_member(auth_client)
    provider = FakeProvider(reply="metformin")

    def fake_build(local_only: bool = False):
        return [provider]

    async def fail(url_or_path, params=None):
        return None

    monkeypatch.setattr(drug_info_service, "_openfda_get", fail)
    monkeypatch.setattr(drug_info_service, "_rxnorm_get", fail)
    monkeypatch.setattr(ai_router, "build_plan", fake_build)

    resp = await auth_client.get(
        f"/api/v1/members/{member_id}/drug-info", params={"medicine": "unknownbrand"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source"] == "ai"
    assert body["generic"] == "metformin"
    assert provider.calls, "AI provider was never called"


async def test_drug_info_unavailable_degrades(auth_client, monkeypatch):
    member_id = await _create_member(auth_client)

    async def fail(url_or_path, params=None):
        return None

    monkeypatch.setattr(drug_info_service, "_openfda_get", fail)
    monkeypatch.setattr(drug_info_service, "_rxnorm_get", fail)

    resp = await auth_client.get(
        f"/api/v1/members/{member_id}/drug-info", params={"medicine": "zzznotadrug"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source"] == "unavailable"
    assert body["generic"] is None


async def test_drug_info_cached_second_lookup_skips_http(auth_client, monkeypatch):
    member_id = await _create_member(auth_client)
    calls = {"n": 0}

    async def fake_openfda(url, params):
        calls["n"] += 1
        return {
            "results": [
                {
                    "openfda": {
                        "brand_name": ["Glucophage"],
                        "generic_name": ["Metformin Hydrochloride"],
                        "manufacturer_name": ["Merck"],
                    },
                }
            ]
        }

    monkeypatch.setattr(drug_info_service, "_openfda_get", fake_openfda)
    first = await auth_client.get(
        f"/api/v1/members/{member_id}/drug-info", params={"medicine": "metformin"}
    )
    assert first.status_code == 200
    second = await auth_client.get(
        f"/api/v1/members/{member_id}/drug-info", params={"medicine": "METFORMIN"}
    )
    assert second.status_code == 200
    assert calls["n"] == 1, "second lookup must come from the cache"
    assert second.json()["brand"] == first.json()["brand"]


async def test_drug_info_requires_medicine_param(auth_client):
    member_id = await _create_member(auth_client)
    resp = await auth_client.get(f"/api/v1/members/{member_id}/drug-info")
    assert resp.status_code == 422


# ── health resources ─────────────────────────────────────────────────


async def test_resources_medlineplus(auth_client, monkeypatch):
    member_id = await _create_member(auth_client)

    async def fake_rxnorm(path, params=None):
        if path.endswith("approximateTerm.json"):
            return {"approximateGroup": {"candidate": [{"rxcui": "6809"}]}}
        return {"properties": {"rxcui": "6809", "name": "Metformin", "tty": "IN"}}

    async def fake_medlineplus(url, params):
        assert params["mainSearchCriteria.v.c"] == "6809"
        return {
            "entry": [
                {
                    "title": "Metformin: MedlinePlus Drug Information",
                    "link": [{"href": "https://medlineplus.gov/druginfo/meds/a696005.html"}],
                    "summary": "Lowers blood glucose.",
                }
            ]
        }

    monkeypatch.setattr(drug_info_service, "_rxnorm_get", fake_rxnorm)
    monkeypatch.setattr(health_resources_service, "_medlineplus_get", fake_medlineplus)

    resp = await auth_client.get(
        f"/api/v1/members/{member_id}/resources",
        params={"term": "metformin", "source": "medlineplus"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source"] == "medlineplus"
    assert body["url"] == "https://medlineplus.gov/druginfo/meds/a696005.html"
    assert "MedlinePlus" in body["title"]
    assert "glucose" in body["summary"]


async def test_resources_dailymed(auth_client, monkeypatch):
    member_id = await _create_member(auth_client)

    async def fake_dailymed(url, params):
        assert params["drug_name"] == "metformin"
        return {"data": [{"title": "Metformin label", "setid": "abc-123"}]}

    monkeypatch.setattr(health_resources_service, "_dailymed_get", fake_dailymed)

    resp = await auth_client.get(
        f"/api/v1/members/{member_id}/resources",
        params={"term": "metformin", "source": "dailymed"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source"] == "dailymed"
    assert body["title"] == "Metformin label"
    assert "setid=abc-123" in body["url"]


async def test_resources_hc_dpd(auth_client, monkeypatch):
    member_id = await _create_member(auth_client)

    async def fake_hcdpd(url, params):
        assert params["din"] == "01234567"
        return [
            {
                "drug_identification_number": "01234567",
                "brand_name": "APO-Metformin",
                "company_name": "Apotex",
                "descriptor": "500 mg tablet",
                "drug_code": 42,
            }
        ]

    monkeypatch.setattr(health_resources_service, "_hcdpd_get", fake_hcdpd)

    resp = await auth_client.get(
        f"/api/v1/members/{member_id}/resources",
        params={"term": "01234567", "source": "hc-dpd"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source"] == "hc-dpd"
    assert body["title"] == "APO-Metformin"
    assert "Apotex" in body["summary"]
    assert "code=42" in body["url"]


async def test_resources_mhra_absolutises_links(auth_client, monkeypatch):
    member_id = await _create_member(auth_client)

    async def fake_mhra(url, params):
        assert "gov.uk" in url
        assert params["q"] == "metformin"
        return {
            "results": [
                {
                    "title": "Class 4 drug alert",
                    "link": "/government/news/metformin-alert",
                    "description": "Recall of one batch.",
                }
            ]
        }

    monkeypatch.setattr(health_resources_service, "_mhra_get", fake_mhra)

    resp = await auth_client.get(
        f"/api/v1/members/{member_id}/resources",
        params={"term": "metformin", "source": "mhra"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source"] == "mhra"
    assert body["url"] == "https://www.gov.uk/government/news/metformin-alert"


async def test_resources_unknown_source_422(auth_client):
    member_id = await _create_member(auth_client)
    resp = await auth_client.get(
        f"/api/v1/members/{member_id}/resources",
        params={"term": "metformin", "source": "wikipedia"},
    )
    assert resp.status_code == 422


async def test_resources_no_match_404(auth_client, monkeypatch):
    member_id = await _create_member(auth_client)

    async def fake_dailymed(url, params):
        return {"data": []}

    monkeypatch.setattr(health_resources_service, "_dailymed_get", fake_dailymed)
    resp = await auth_client.get(
        f"/api/v1/members/{member_id}/resources",
        params={"term": "zzznotadrug", "source": "dailymed"},
    )
    assert resp.status_code == 404


# ── drug-catalog search (Jan Aushadhi) ───────────────────────────────


async def test_drug_search_finds_seeded_row(auth_client, session_factory):
    async with session_factory() as db:
        seeded = await local_drug_service.seed_local_drugs(db)
        await db.commit()
    assert seeded >= 600, "bundled official PMBJP export should carry 600+ products"

    resp = await auth_client.get("/api/v1/drugs/search", params={"q": "metformin"})
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert rows, "official catalog must contain metformin products"
    assert any("Metformin" in r["name"] for r in rows)
    assert any(r["price"] is not None for r in rows), "official rows carry MRP"

    # Query ignores dosage/form words via normalization.
    resp2 = await auth_client.get("/api/v1/drugs/search", params={"q": "metformin 850 tablet"})
    assert any("Metformin" in r["name"] for r in resp2.json())


async def test_drug_search_parses_composition(tmp_path, auth_client, session_factory):
    """Legacy sample-shaped CSVs (with composition) keep ingredient parsing."""
    sample = tmp_path / "sample.csv"
    sample.write_text(
        "product_id,name,composition,price,package\n"
        "1,Metformin 500mg Tablet,Metformin (500mg),3.2,10's\n"
        "2,Glimepiride + Metformin Tablet,Glimepiride (1mg) + Metformin (500mg),4.5,10's\n"
    )
    async with session_factory() as db:
        seeded = await local_drug_service.seed_local_drugs(db, sample)
        await db.commit()
    assert seeded == 2

    resp = await auth_client.get("/api/v1/drugs/search", params={"q": "metformin"})
    rows = resp.json()
    top = next(r for r in rows if r["name"] == "Metformin 500mg Tablet")
    assert top["ingredients"] == [{"name": "Metformin", "strength": "500mg"}]
    assert top["price"] == 3.2
    combo = next(r for r in rows if "+" in r["name"])
    assert [i["name"] for i in combo["ingredients"]] == ["Glimepiride", "Metformin"]


async def test_drug_search_requires_auth_and_min_query(client):
    resp = await client.get("/api/v1/drugs/search", params={"q": "metformin"})
    assert resp.status_code == 401
