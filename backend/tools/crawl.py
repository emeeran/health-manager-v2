#!/usr/bin/env python3
"""Crawl 1mg.com and apollopharmacy.in drug indexes into a structured CSV.

- Discovery via their public sitemaps (drug URLs only).
- Checkpointed in SQLite (data/crawl.db) -> safe to stop/resume.
- Extracts factual fields only (names, composition, price, uses, side-effect
  list items, safety labels). Long editorial prose is NOT stored.
- Output: data/rows.jsonl + data/medicine_full.csv

Usage:
  python3 crawl.py discover --site 1mg|apollo|all [--data DIR]
  python3 crawl.py crawl   --site 1mg|apollo|all [--workers 8] [--delay 0.3] [--limit N] [--export]
  python3 crawl.py refresh [--days 7] [--limit N]     re-enqueue pages last crawled before N days ago
  python3 crawl.py export
  python3 crawl.py status

Data dir defaults to ./data next to this script; override with --data DIR
or the MEDICINE_CRAWLER_DATA_DIR environment variable. The last line of a
crawl/refresh run is always ``RESULT {...}`` for callers that parse it.
"""

import csv
import gzip
import html as htmllib
import json
import os
import re
import sqlite3
import ssl
import sys
import threading
import time
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("MEDICINE_CRAWLER_DATA_DIR") or os.path.join(BASE, "..", "data", "medicine-crawler")
DB_PATH = os.path.join(DATA, "crawl.db")
JSONL_PATH = os.path.join(DATA, "rows.jsonl")
CSV_PATH = os.path.join(DATA, "medicine_full.csv")


def _set_data_dir(path: str) -> None:
    global DATA, DB_PATH, JSONL_PATH, CSV_PATH
    DATA = path
    DB_PATH = os.path.join(DATA, "crawl.db")
    JSONL_PATH = os.path.join(DATA, "rows.jsonl")
    CSV_PATH = os.path.join(DATA, "medicine_full.csv")

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
CTX = ssl.create_default_context()

_lock = threading.Lock()
_stats = {"fetched": 0, "ok": 0, "err": 0, "consecutive_blocks": 0}
_stats_lock = threading.Lock()

FIELDS = [
    "source", "url", "brand_name", "generic_name", "manufacturer",
    "pack_size", "price_mrp", "price_selling", "discount_pct", "currency",
    "dosage_form", "uses", "side_effects", "warnings_general",
    "safety_alcohol", "safety_pregnancy", "safety_breastfeeding",
    "safety_driving", "safety_liver", "safety_kidney",
    "habit_forming", "therapeutic_class", "prescription_required",
    "category_path", "description_brief", "page_last_updated",
]

# ---------------------------------------------------------------- storage

_tls = threading.local()


def tdb():
    """Per-thread SQLite connection (sqlite3 objects are not thread-safe)."""
    if not hasattr(_tls, "conn"):
        _tls.conn = db()
    return _tls.conn


def db():
    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS urls ("
        " url TEXT PRIMARY KEY, site TEXT, status TEXT, tries INTEGER DEFAULT 0,"
        " error TEXT, fetched_at REAL)")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS rows (url TEXT PRIMARY KEY, data TEXT)")
    return conn


def add_urls(conn, site, urls):
    with conn:
        conn.executemany(
            "INSERT OR IGNORE INTO urls (url, site, status) VALUES (?, ?, 'pending')",
            ((u, site) for u in urls))


def mark(conn, url, status, error=None):
    with conn:
        conn.execute(
            "UPDATE urls SET status=?, tries=tries+1, error=?, fetched_at=? WHERE url=?",
            (status, error, time.time(), url))


def save_row(conn, url, data):
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO rows (url, data) VALUES (?, ?)",
            (url, json.dumps(data, ensure_ascii=False)))
    with _stats_lock:
        with open(JSONL_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False) + "\n")

# ---------------------------------------------------------------- fetching

def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip",
    })
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as resp:
        raw = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        return resp.status, raw.decode("utf-8", errors="replace")


def fetch_retry(url, max_tries=5):
    """Returns (html, None) or (None, errmsg). Backs off on 429/5xx."""
    err = None
    for t in range(max_tries):
        try:
            status, body = fetch(url)
            return body, None
        except urllib.error.HTTPError as e:
            err = f"HTTP {e.code}"
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(min(2 ** t * 5, 120))
                continue
            if e.code == 403:
                with _stats_lock:
                    _stats["consecutive_blocks"] += 1
                return None, err
            return None, err
        except Exception as e:  # URLError, timeout, ssl...
            err = str(e)[:120]
            time.sleep(min(2 ** t * 3, 60))
    return None, err

# ---------------------------------------------------------------- discovery

SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


def parse_sitemap(xml_text):
    """Returns (urls, child_sitemaps)."""
    root = ET.fromstring(xml_text)
    urls, children = [], []
    if root.tag == SITEMAP_NS + "sitemapindex":
        for sm in root.findall(f"{SITEMAP_NS}sitemap"):
            loc = sm.findtext(f"{SITEMAP_NS}loc")
            if loc:
                children.append(loc.strip())
    else:
        for u in root.findall(f"{SITEMAP_NS}url"):
            loc = u.findtext(f"{SITEMAP_NS}loc")
            if loc:
                urls.append(loc.strip())
    return urls, children


def fetch_sitemap(url):
    _, body = fetch(url)
    return parse_sitemap(body)


def discover_1mg(conn):
    _, body = fetch("https://www.1mg.com/sitemap.xml")
    _, children = parse_sitemap(body)
    drug_maps = [c for c in children if "sitemap_drugs_" in c]
    urls = []
    for sm in drug_maps:
        u, _ = fetch_sitemap(sm)
        urls.extend(x for x in u if "/drugs/" in x)
    add_urls(conn, "1mg", urls)
    return len(urls)


def discover_apollo(conn):
    _, body = fetch("https://www.apollopharmacy.in/sitemap/sitemap-master.xml")
    _, children = parse_sitemap(body)
    # English pharma catalogs only (skip hindi/tamil/telugu mirrors and non-drug sitemaps)
    targets = [c for c in children if re.match(
        r".*/sitemap-(pharma-(?:rx|otc))\.xml$", c)]
    urls = []
    for sm in targets:
        u, sub = fetch_sitemap(sm)
        urls.extend(u)
        for s2 in sub:  # pharma sitemaps may be nested indexes
            u2, _ = fetch_sitemap(s2)
            urls.extend(u2)
    urls = [u for u in urls if "/medicine/" in u]
    add_urls(conn, "apollo", urls)
    return len(urls)

# ---------------------------------------------------------------- parsing

TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")


def strip_html(s, cap=400):
    if not s:
        return ""
    s = htmllib.unescape(TAG_RE.sub(" ", str(s)))
    s = WS_RE.sub(" ", s).strip()
    return s[:cap].strip()


def li_items(html_frag, cap_each=200, max_items=15):
    """Text of <li> elements in an HTML fragment."""
    items = re.findall(r"<li[^>]*>(.*?)</li>", html_frag or "", re.S)
    out = []
    for it in items:
        t = strip_html(it, cap_each)
        if t:
            out.append(t)
        if len(out) >= max_items:
            break
    return out


# ---- 1mg ----

def parse_1mg(html_text, url):
    i = html_text.find("window.__INITIAL_STATE__ = ")
    if i < 0:
        return None
    i += len("window.__INITIAL_STATE__ = ")
    try:
        state, _ = json.JSONDecoder().raw_decode(html_text[i:])
    except Exception:
        return None
    sd = (state.get("drugPageReducer") or {}).get("staticData") or {}
    dyn = (state.get("drugPageReducer") or {}).get("dynamicData") or {}
    if not sd.get("productConfig"):
        return None

    row = {f: "" for f in FIELDS}
    row["source"] = "1mg"
    row["url"] = url
    row["brand_name"] = strip_html(sd["productConfig"].get("entity_name", ""), 150)

    # general info: composition + manufacturer
    for attr in (sd.get("generalInformation") or {}).get("attributesData", []):
        label = strip_html(attr.get("label", ""), 60).lower()
        val = strip_html(attr.get("value", ""), 300)
        if not val:
            continue
        if "contains" in label or "composition" in label:
            row["generic_name"] = val
        elif "manufacturer" in label or "marketer" in label:
            row["manufacturer"] = val

    # fact box: habit forming, therapeutic class, pack forms
    for attr in (sd.get("factBoxData") or {}).get("attributesData", []):
        label = strip_html(attr.get("label", ""), 60).lower()
        val = strip_html(attr.get("value", ""), 150)
        if "habit" in label:
            row["habit_forming"] = val
        elif "therapeutic" in label:
            row["therapeutic_class"] = val
        elif "pack" in label:
            row["dosage_form"] = val

    # price + pack
    pd = dyn.get("priceData") or {}
    row["pack_size"] = strip_html(pd.get("packSizes", ""), 100)
    pb = dyn.get("priceBox") or {}
    for offer in pb.get("priceList", []):
        mrp = ((offer.get("mrp") or {}).get("price") or "").replace("₹", "").replace(",", "").strip()
        dis = ((offer.get("discount") or {}).get("price") or "").replace("₹", "").replace(",", "").strip()
        dpct = strip_html(((offer.get("discount") or {}).get("displayText") or ""), 30)
        m = re.search(r"\d+", dpct)
        if mrp:
            row["price_mrp"] = mrp
        if dis:
            row["price_selling"] = dis
        if m:
            row["discount_pct"] = m.group(0)
    row["currency"] = "INR" if row["price_mrp"] or row["price_selling"] else ""

    # uses (list of conditions)
    uses = li_items((sd.get("productUses") or {}).get("content", ""), cap_each=150)
    row["uses"] = "; ".join(uses)

    # side effects (list items)
    se_html = (sd.get("sideEffect") or {}).get("content", "")
    se = li_items(se_html, cap_each=100, max_items=25)
    if not se:  # some pages inline them as bold text
        se = [strip_html(x, 100) for x in re.findall(r"<b>(.*?)</b>", se_html)]
    row["side_effects"] = "; ".join(se[:25])

    # safety advice: label -> status/text
    for w in (sd.get("safetyAdvice") or {}).get("warnings", []):
        label = strip_html(w.get("imageCaption", ""), 60).lower()
        txt = " ".join(strip_html(x.get("displayText", ""), 250)
                       for x in w.get("descriptions", []) if isinstance(x, dict))
        if not txt:
            txt = strip_html(w.get("description", "") if isinstance(w.get("description"), str) else "", 250)
        key = None
        if "alcohol" in label:
            key = "safety_alcohol"
        elif "pregnan" in label:
            key = "safety_pregnancy"
        elif "lactation" in label or "breast" in label:
            key = "safety_breastfeeding"
        elif "driving" in label:
            key = "safety_driving"
        elif "kidney" in label:
            key = "safety_kidney"
        elif "liver" in label:
            key = "safety_liver"
        if key and txt:
            row[key] = txt

    row["prescription_required"] = "Yes" if (dyn.get("rxCommunicationExperimentData") or {}).get("rxCommunicationData") else ""
    row["category_path"] = " > ".join(
        strip_html(b.get("header", ""), 60) for b in sd.get("breadcrumbs", []) if b.get("header"))
    upd = ((sd.get("authorsData") or {}).get("lastUpdate") or {}).get("text", "")
    row["page_last_updated"] = strip_html(upd.replace("Last updated", ""), 40)
    return row


# ---- Apollo ----

def apollo_sections(html_text):
    """Grab visible section HTML (side effects list, directions, storage)."""
    def section(title_re):
        m = re.search(
            r"<h[23][^>]*>\s*(?:<[^>]*>)*\s*" + title_re +
            r".*?</h[23]>(.*?)(?=<h[23]|$)", html_text, re.I | re.S)
        return m.group(1) if m else ""
    return section


def parse_apollo(html_text, url):
    schemas = dict(re.findall(
        r'<script id="([\w-]+)" type="application/ld\+json">(.*?)</script>',
        html_text, re.S))
    drug = None
    faq = []
    if "drug-schema" in schemas:
        try:
            d = json.loads(htmllib.unescape(schemas["drug-schema"]))
            drug = d.get("mainEntity") or {}
        except Exception:
            pass
    if "faq-schema" in schemas:
        try:
            faq = json.loads(htmllib.unescape(schemas["faq-schema"])).get("mainEntity", [])
        except Exception:
            pass
    if drug is None:
        return None

    row = {f: "" for f in FIELDS}
    row["source"] = "apollo"
    row["url"] = url
    row["brand_name"] = strip_html(drug.get("proprietaryName") or drug.get("name"), 150)
    row["generic_name"] = strip_html(drug.get("nonProprietaryName"), 200)
    row["manufacturer"] = strip_html((drug.get("manufacturer") or {}).get("legalName"), 150)
    row["dosage_form"] = strip_html(drug.get("dosageForm") or drug.get("administrationRoute"), 60)
    row["prescription_required"] = "Yes" if "prescription" in str(drug.get("prescriptionStatus", "")).lower() else "No"

    offer = drug.get("offers") or {}
    price = offer.get("price")
    if price not in (None, "", 0):
        row["price_selling"] = str(price)
        row["currency"] = offer.get("priceCurrency", "INR")
        # RSC payload carries the authoritative mrp/sellingPrice pair
        # (first occurrence = main product, later ones are related items)
        m_mrp = re.search(r'mrp\\?":\\?"?([\d.]+)', html_text)
        m_sell = re.search(r'sellingPrice\\?":\\?"?([\d.]+)', html_text)
        if m_sell:
            row["price_selling"] = m_sell.group(1)
        if m_mrp:
            row["price_mrp"] = m_mrp.group(1)
        bn = strip_html(row["brand_name"], 80)
        # pack size: Apollo appends pack count as "Product 10's"; prefer that
        # over strength tokens like "30 Capsule" in the middle of the name
        m2 = re.findall(r"(tablets?|capsules?|sachets?|softgels?)\s*(\d+)\s*(?:'s)?", bn, re.I)
        if m2:
            u, n = m2[-1]
            row["pack_size"] = f"{n} {u}"
        else:
            m = None
            for m in re.finditer(r"(\d+)\s*(ml|gm|g|sprays?|drops?|tablets?|capsules?)\b", bn, re.I):
                pass
            if m:
                row["pack_size"] = f"{m.group(1)} {m.group(2)}"

    # warnings (short factual labels; capped)
    row["warnings_general"] = strip_html(drug.get("warning"), 400)
    row["safety_alcohol"] = strip_html(drug.get("alcoholWarning"), 250)
    row["safety_pregnancy"] = strip_html(drug.get("pregnancyWarning"), 250)
    row["safety_breastfeeding"] = strip_html(drug.get("breastfeedingWarning"), 250)
    row["description_brief"] = strip_html(drug.get("description"), 400)

    # uses: first FAQ answer ("What is the use of ...")
    # side effects: side-effect FAQ answer (section itself is client-rendered,
    # absent from raw HTML); fall back to visible HTML list if present
    for q in faq:
        qn = strip_html(q.get("name", ""), 120).lower()
        ans = strip_html((q.get("acceptedAnswer") or {}).get("text", ""), 300)
        if not ans:
            continue
        if "side effect" in qn or "side-effects" in qn:
            row["side_effects"] = ans
        elif ("use of" in qn or "used for" in qn or "used to" in qn) and not row["uses"]:
            row["uses"] = ans

    if not row["side_effects"]:
        sec = apollo_sections(html_text)
        se_html = sec(r"Side\s*Effects")
        row["side_effects"] = "; ".join(li_items(se_html, cap_each=100, max_items=20))

    # category from breadcrumb
    if "breadcrumb-schema" in schemas:
        try:
            bc = json.loads(htmllib.unescape(schemas["breadcrumb-schema"]))
            items = [strip_html(i.get("name", ""), 60)
                     for i in bc.get("itemListElement", [])]
            row["category_path"] = " > ".join(x for x in items if x)
        except Exception:
            pass
    return row

# ---------------------------------------------------------------- crawl

PARSERS = {"1mg": parse_1mg, "apollo": parse_apollo}


def crawl_site(conn, site, workers, delay, limit):
    rows = conn.execute(
        "SELECT url FROM urls WHERE site=? AND status='pending' LIMIT ?",
        (site, limit or 10**9)).fetchall()
    urls = [r[0] for r in rows]
    total = len(urls)
    print(f"[{site}] {total} pending URLs", flush=True)
    if not urls:
        return

    def work(u):
        # politeness pause if the site is blocking us
        with _stats_lock:
            blocked = _stats["consecutive_blocks"]
        if blocked >= 15:
            print(f"[{site}] 15 consecutive blocks - pausing 10 min", flush=True)
            time.sleep(600)
            with _stats_lock:
                _stats["consecutive_blocks"] = 0
        html_text, err = fetch_retry(u)
        with _stats_lock:
            _stats["fetched"] += 1
            n = _stats["fetched"]
            if n % 500 == 0:
                print(f"[{site}] progress {n}/{total} "
                      f"(ok={_stats['ok']} err={_stats['err']})", flush=True)
        if html_text is None:
            with _stats_lock:
                _stats["err"] += 1
                _stats["consecutive_blocks"] = 0
            mark(tdb(), u, "error", err)
            return
        with _stats_lock:
            _stats["ok"] += 1
            _stats["consecutive_blocks"] = 0
        try:
            row = PARSERS[site](html_text, u)
            if row:
                save_row(tdb(), u, row)
                mark(tdb(), u, "done")
            else:
                mark(tdb(), u, "unparsed", "no data found")
        except Exception as e:
            mark(tdb(), u, "unparsed", str(e)[:120])
        time.sleep(delay)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(work, urls))
    print(f"[{site}] done: ok={_stats['ok']} err={_stats['err']}", flush=True)

# ---------------------------------------------------------------- export

def export():
    conn = db()
    out = []
    for url, data in conn.execute("SELECT url, data FROM rows"):
        out.append(json.loads(data))
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(out)
    by = {}
    for r in out:
        by[r["source"]] = by.get(r["source"], 0) + 1
    print(f"exported {len(out)} rows -> {CSV_PATH} {by}", flush=True)

# ---------------------------------------------------------------- main

def main():
    def opt(name, default, cast=str):
        return cast(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default

    _set_data_dir(opt("--data", DATA))
    os.makedirs(DATA, exist_ok=True)
    # command word = first arg that is neither a flag nor a flag's value
    cmd = ""
    skip = False
    for a in sys.argv[1:]:
        if skip:
            skip = False
            continue
        if a == "--data":
            skip = True
            continue
        if not a.startswith("--"):
            cmd = a
            break
    conn = db()

    def print_result(payload: dict) -> None:
        print("RESULT " + json.dumps(payload), flush=True)

    site = opt("--site", "all")
    if cmd == "discover":
        n = 0
        if site in ("1mg", "all"):
            n += discover_1mg(conn)
        print("1mg urls added")
        if site in ("apollo", "all"):
            n += discover_apollo(conn)
        print("apollo urls added")
        print(f"total new urls: {n}")
    elif cmd == "crawl":
        if site in ("1mg", "all"):
            crawl_site(conn, "1mg", opt("--workers", 8, int),
                   opt("--delay", 0.3, float), opt("--limit", 0, int))
        if site in ("apollo", "all"):
            crawl_site(conn, "apollo", opt("--workers", 8, int),
                   opt("--delay", 0.3, float), opt("--limit", 0, int))
        if "--export" in sys.argv:
            export()
        print_result({"cmd": "crawl", "fetched": _stats["fetched"],
                      "ok": _stats["ok"], "err": _stats["err"]})
    elif cmd == "refresh":
        days = opt("--days", 7, int)
        limit = opt("--limit", 1000, int)
        cutoff = time.time() - max(1, days) * 86400
        q = ("SELECT url FROM urls WHERE status='done' AND fetched_at IS NOT NULL "
             "AND fetched_at < ?")
        params: list = [cutoff]
        if site != "all":
            q += " AND site=?"
            params.append(site)
        q += " LIMIT ?"
        params.append(limit)
        stale = [r[0] for r in conn.execute(q, params)]
        with conn:
            conn.executemany("UPDATE urls SET status='pending' WHERE url=?",
                             ((u,) for u in stale))
        print(f"re-enqueued {len(stale)} pages older than {days}d")
        print_result({"cmd": "refresh", "requeued": len(stale)})
    elif cmd == "export":
        export()
    elif cmd == "status":
        for s, st, c in conn.execute("SELECT site, status, COUNT(*) FROM urls GROUP BY site, status"):
            print(f"{s:8s} {st:10s} {c}")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
