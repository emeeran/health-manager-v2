"""Crawler drug catalog: sync from crawler checkpoint DB + /drugs integration.

The crawler subprocess is never run here — tests build a tiny checkpoint
SQLite with the same ``rows`` table shape and exercise sync, search, and
pharmacy-offer matching against it.
"""

import json
import sqlite3

import pytest
from sqlalchemy import select

from app.models import CrawlerDrug
from app.services import crawler_drug_service, local_drug_service

# Duzela M rows in the same JSON shape tools/crawl.py writes.
_ROWS = [
    (
        "https://www.1mg.com/drugs/duzela-m-30-capsule-dr-161900",
        {
            "source": "1mg",
            "brand_name": "Duzela M 30 Capsule DR",
            "generic_name": "Duloxetine (30mg)+ Methylcobalamin (1500mcg)",
            "manufacturer": "Sun Pharmaceutical Industries Ltd",
            "pack_size": "10 Capsule DR",
            "price_mrp": "231",
            "price_selling": "212",
            "uses": "Neuropathic pain",
        },
    ),
    (
        "https://www.apollopharmacy.in/medicine/duzela-m-30mg-capsule",
        {
            "source": "apollo",
            "brand_name": "Duzela M 30 Capsule 10's",
            "generic_name": "DULOXETINE-30MG+METHYLCOBALAMIN-1500MCG",
            "manufacturer": "Sun Pharmaceutical Industries Ltd",
            "pack_size": "10 Capsule",
            "price_mrp": "231",
            "price_selling": "231",
            "uses": "Neuropathic pain",
        },
    ),
    (
        "https://www.apollopharmacy.in/medicine/dolo-650-tablet",
        {
            "source": "apollo",
            "brand_name": "Dolo 650 Tablet",
            "generic_name": "PARACETAMOL-650MG",
            "manufacturer": "Micro Labs Ltd",
            "pack_size": "15 Tablet",
            "price_selling": "34",
            "uses": "Pain relief; Fever",
        },
    ),
    (  # no brand name — sync must skip it
        "https://www.apollopharmacy.in/medicine/broken-page",
        {"source": "apollo", "brand_name": ""},
    ),
]


@pytest.fixture()
def crawler_db(tmp_path):
    """A checkpoint SQLite with the crawler's rows table."""
    path = tmp_path / "crawl.db"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE rows (url TEXT PRIMARY KEY, data TEXT)"
    )
    conn.executemany(
        "INSERT INTO rows (url, data) VALUES (?, ?)",
        [(url, json.dumps(data)) for url, data in _ROWS],
    )
    conn.commit()
    conn.close()
    return path


async def _sync(session_factory, crawler_db):
    async with session_factory() as db:
        outcome = await crawler_drug_service.sync_from_crawler_db(db, crawler_db)
    return outcome


async def test_sync_upserts_and_skips_brandless(session_factory, crawler_db):
    outcome = await _sync(session_factory, crawler_db)
    assert outcome["status"] == "ok"
    assert outcome["rows_seen"] == len(_ROWS)
    assert outcome["synced"] == 3  # brandless row skipped

    async with session_factory() as db:
        rows = (await db.scalars(select(CrawlerDrug))).all()
        assert {r.source for r in rows} == {"1mg", "apollo"}
        duzela = [r for r in rows if r.price_selling == 212]
        assert duzela[0].name_normalized == local_drug_service.normalize_drug_name(
            "Duzela M 30 Capsule DR"
        )


async def test_sync_is_idempotent_and_updates_prices(session_factory, crawler_db):
    await _sync(session_factory, crawler_db)

    # crawler re-crawls Duzela at a new price → re-sync updates in place
    conn = sqlite3.connect(crawler_db)
    conn.execute(
        "UPDATE rows SET data=? WHERE url LIKE '%1mg%'",
        (json.dumps({**_ROWS[0][1], "price_selling": "199"}),),
    )
    conn.commit()
    conn.close()

    outcome = await _sync(session_factory, crawler_db)
    assert outcome["synced"] == 3  # no duplicates

    async with session_factory() as db:
        rows = (await db.scalars(select(CrawlerDrug))).all()
        assert len(rows) == 3
        prices = {r.url: r.price_selling for r in rows}
        assert prices[_ROWS[0][0]] == 199


async def test_offers_exact_first_then_partial_topup(session_factory, crawler_db):
    await _sync(session_factory, crawler_db)
    async with session_factory() as db:
        offers = await crawler_drug_service.offers_for(db, "Duzela M 30 Capsule DR")
    # 1mg row normalizes identically → exact; the apollo pack-suffix variant
    # normalizes differently → partial top-up, cheapest overall first.
    assert len(offers) == 2
    assert offers[0]["match"] == "exact"
    assert offers[0]["price"] == 212
    assert {o["catalog"] for o in offers} == {"1mg", "apollo"}


async def test_offers_partial_match(session_factory, crawler_db):
    await _sync(session_factory, crawler_db)
    async with session_factory() as db:
        offers = await crawler_drug_service.offers_for(db, "Duzela M Capsule")
    assert offers
    assert all(o["match"] == "partial" for o in offers)


async def test_offers_unmatched_is_empty(session_factory, crawler_db):
    await _sync(session_factory, crawler_db)
    async with session_factory() as db:
        offers = await crawler_drug_service.offers_for(db, "Totally Unknown Drug")
    assert offers == []


async def test_search_endpoint_includes_crawler_rows(session_factory, crawler_db, auth_client):
    await _sync(session_factory, crawler_db)
    resp = await auth_client.get("/api/v1/drugs/search", params={"q": "duzela"})
    assert resp.status_code == 200, resp.text
    items = resp.json()
    crawler_items = [i for i in items if i["catalog"] in ("1mg", "apollo")]
    assert len(crawler_items) == 2
    one = crawler_items[0]
    assert one["product_id"] is None
    assert one["url"].startswith("https://")
    assert one["price"] is not None
    ja = [i for i in items if i["catalog"] == "jan_aushadhi"]
    assert all("url" not in i or i["url"] is None for i in ja) or ja == []


async def test_price_compare_attaches_pharmacy_offers(session_factory, crawler_db, auth_client):
    await _sync(session_factory, crawler_db)
    resp = await auth_client.post(
        "/api/v1/drugs/price-compare",
        json={"medicines": ["Duzela M 30 Capsule DR"], "narrate": False},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    item = body["items"][0]
    offers = item["pharmacy_offers"]
    assert len(offers) == 2
    assert body["offers_matched_count"] == 1
    assert offers[0]["price"] == 212


async def test_sync_without_database_reports_status(session_factory, tmp_path):
    async with session_factory() as db:
        outcome = await crawler_drug_service.sync_from_crawler_db(
            db, tmp_path / "missing.db"
        )
    assert outcome == {"status": "no_database", "synced": 0, "rows_seen": 0}
