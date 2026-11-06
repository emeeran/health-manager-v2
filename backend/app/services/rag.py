"""Local RAG grounding over your own medical reference (FTS5).

The index is NOT distributed — build it from your own PDF:
    uv run python -m app.scripts.seed_rag_index /path/to/reference.pdf
Until the index file exists the feature is inert (chat works ungrounded).
"""

import sqlite3
from pathlib import Path

from app.core.config import get_settings

_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5(
    text, page UNINDEXED, source UNINDEXED,
    tokenize = 'unicode61 remove_diacritics 2'
);
"""


_STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "with", "for",
    "is", "are", "was", "were", "what", "how", "when", "where", "who", "which",
    "can", "could", "should", "does", "do", "did", "patient", "tell", "me", "about",
    "i", "my", "we", "our", "you", "your", "it", "its", "at", "by", "from", "as",
})


def index_path() -> Path:
    return Path(get_settings().RAG_INDEX_PATH)


def rag_available() -> bool:
    return get_settings().RAG_ENABLED and index_path().is_file()


def open_index(readonly: bool = True) -> sqlite3.Connection:
    path = index_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if readonly:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(path)
        conn.executescript(_SCHEMA)
    return conn


def chunk_pages(
    pages: list[tuple[int, str]],
    source: str,
    chunk_chars: int = 2000,
    overlap_chars: int = 200,
) -> list[dict]:
    """Split page texts into overlapping chunks (page-anchored)."""
    chunks = []
    stride = max(100, chunk_chars - overlap_chars)
    for page_num, text in pages:
        text = " ".join(text.split())
        if len(text.strip()) < 20:
            continue
        page_chunks_count = 0
        for start in range(0, len(text), stride):
            piece = text[start : start + chunk_chars]
            # Skip tiny trailing slivers if we already chunked this page
            if len(piece.strip()) < 50 and page_chunks_count > 0:
                continue
            if len(piece.strip()) < 20:
                continue
            chunks.append({"text": piece, "page": page_num, "source": source})
            page_chunks_count += 1
    return chunks


def build_index(pages: list[tuple[int, str]], source: str) -> int:
    """(Re)build the index from page texts; returns chunk count."""
    conn = open_index(readonly=False)
    try:
        conn.execute("DROP TABLE IF EXISTS chunks")
        conn.executescript(_SCHEMA)
        chunks = chunk_pages(pages, source)
        conn.executemany(
            "INSERT INTO chunks (text, page, source) VALUES (?, ?, ?)",
            [(c["text"], c["page"], c["source"]) for c in chunks],
        )
        conn.commit()
        return len(chunks)
    finally:
        conn.close()


def search(query: str, top_k: int | None = None) -> list[dict]:
    """FTS5 BM25-ranked snippets; empty result when inert/no hits."""
    if not rag_available():
        return []
    settings = get_settings()
    k = top_k or settings.RAG_TOP_K
    # Sanitize into FTS5 quoted terms joined with OR (AND semantics miss
    # when any question word is absent from the corpus; bm25 ranks the
    # relevant chunks up regardless). Prune conversational stopwords when
    # possible to focus ranking on clinical terminology.
    raw_tokens = "".join(ch if ch.isalnum() else " " for ch in query).lower().split()
    filtered = [t for t in raw_tokens if t not in _STOPWORDS and len(t) > 1]
    tokens = filtered if filtered else [t for t in raw_tokens if len(t) > 1]
    terms = " OR ".join(f'"{t}"' for t in tokens)
    if not terms:
        return []
    conn = open_index()
    try:
        rows = conn.execute(
            "SELECT text, page, source, bm25(chunks) AS rank "
            "FROM chunks WHERE chunks MATCH ? ORDER BY rank LIMIT ?",
            (terms, k),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()
    max_chars = settings.RAG_MAX_CHARS
    out = []
    for text, page, source, _rank in rows:
        snippet = text[:max_chars]
        out.append({"text": snippet, "page": page, "source": source})
    return out


def grounding_block(query: str) -> tuple[str, list[dict]]:
    """Prompt block + citation list, or ("", []) when nothing grounds."""
    hits = search(query)
    if not hits:
        return "", []
    lines = [
        f"[{i + 1}] ({hit['source']}, page {hit['page']}) {hit['text']}"
        for i, hit in enumerate(hits)
    ]
    block = (
        "Reference excerpts from the household's medical reference "
        "(cite these when you rely on them):\n" + "\n".join(lines)
    )
    citations = [
        {"source": hit["source"], "page": hit["page"], "snippet": hit["text"][:200]}
        for hit in hits
    ]
    return block, citations


def status() -> dict:
    settings = get_settings()
    available = rag_available()
    count = 0
    if available:
        conn = open_index()
        try:
            count = conn.execute("SELECT count(*) FROM chunks").fetchone()[0]
        finally:
            conn.close()
    return {
        "enabled": settings.RAG_ENABLED,
        "indexed": available,
        "chunks": count,
    }
