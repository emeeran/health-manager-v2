---
title: "CMDT 2026 Local RAG: Implementation & Testing Task List"
date: 2026-11-06
tags:
  - tasklist
  - rag
  - cmdt
  - health-manager
  - testing
status: completed
---

# CMDT 2026 Local RAG: Implementation & Testing Task List

Related docs: [[rag-cmdt-plan]] | [[PLAN]] | [[TASKLIST]]

---

## 1. Overview & Scope

Task breakdown for indexing, optimizing, and thoroughly validating RAG grounding over `CURRENT Medical Diagnosis & Treatment 2026` (1,967 pages, 102 MB) in the Health Manager application.

- **Target Reference**: `/home/em/nas/EBOOKS/BOOK COLLECTIONS/Sorted/Fav Books/CURRENT Medical Diagnosis & Treatment-2026.pdf`
- **Destination Store**: `backend/data/rag-index.sqlite`
- **Search Engine**: SQLite FTS5 with BM25 ranking

---

## 2. Task Breakdown

### Phase 1: Refinements & Quality Tuning 🔧
- [x] **Add citation source field**: Include `source: hit["source"]` in `rag.grounding_block()` citations payload so UI renders `CMDT 2026` rather than generic `Reference`.
- [x] **Extraction progress logging**: Add page count ticker to `backend/app/scripts/seed_rag_index.py` for long PDF runs.
- [x] **Chunking overlap**: Add a 200-character sliding overlap to `chunk_pages()` in `rag.py` to prevent clinical sentences and drug dosages from being cut across chunk boundaries.
- [x] **Stopword & query pruning**: Filter conversational filler words ("what", "are", "the", "for", "when") before building the FTS5 `OR` query, ensuring BM25 weights focus on clinical terms (e.g., "hypertension", "metformin", "microalbuminuria").

### Phase 2: Index Generation & Seeding 🚀
- [x] **Pre-flight storage check**: Verify write permissions and disk space in `backend/data/` (59 GB available, 19 MB consumed).
- [x] **Run seed script**: Indexed 6,453 chunks from 1,960 pages into `backend/data/rag-index.sqlite` in 25 seconds.
  ```bash
  cd /home/em/code/health-manager-v2/backend
  uv run python -m app.scripts.seed_rag_index \
    '/home/em/nas/EBOOKS/BOOK COLLECTIONS/Sorted/Fav Books/CURRENT Medical Diagnosis & Treatment-2026.pdf' \
    --source-name "CMDT 2026"
  ```
- [x] **Index validation**: Confirmed chunk count (`chunks: 6453`, `indexed: True`) and SQLite table integrity.
  ```bash
  cd /home/em/code/health-manager-v2/backend
  uv run python -c "from app.services import rag; print(rag.status())"
  ```

### Phase 3: Automated Unit & Integration Tests 🧪
- [x] **Parity & Chat grounding tests**: Suite passes in `backend/tests/test_deferred_parity.py`.
- [x] **Chunking overlap unit test**: Verified in `backend/tests/test_rag.py::test_chunk_pages_with_overlap`.
- [x] **Clinical retrieval benchmark**: Verified against Diabetes (p. 50), Anaphylaxis (p. 150), and Stage 2 HTN (p. 250) in `backend/tests/test_rag.py::test_clinical_retrieval_synthetic_benchmark`.
- [x] **Copyright invariant audit test**: Verified in `backend/tests/test_rag.py::test_metadata_only_citations_invariant` (`metadata_only_citations()` strips full chunk text).
- [x] **FTS5 syntax safety test**: Verified in `backend/tests/test_rag.py::test_fts5_syntax_safety_and_stopwords` (malformed operators `AND`, `OR`, `NOT`, wildcards, quotes return cleanly).

### Phase 4: Full Stack E2E & UI Verification 🖥️
- [x] **Dev server start**: Verified running (`uvicorn` port 8002 / `vite` port 3000).
- [x] **Chat prompt grounding verification**: Verified end-to-end via `chat_stream`—prompt successfully injects CMDT reference block and completes with 4 citations attached.
- [x] **UI inspection**: `<SourcesList>` in `frontend/src/pages/chat.tsx` renders `<BookOpen /> CMDT 2026 · p. <number>` pill with expandable snippet.
- [x] **Verification model check**: `schedule_verification` hook properly receives grounded response and audit metadata.

---

## 3. Test Matrix & Verification Commands

| Scope | Command | Pass Criteria | Status |
| :--- | :--- | :--- | :--- |
| **Lint & Formatting** | `cd backend && uv run ruff check app/services/rag.py app/scripts/seed_rag_index.py tests/test_rag.py` | 0 errors | Passed ✅ |
| **Unit Test Suite** | `cd backend && uv run pytest tests/test_rag.py tests/test_deferred_parity.py -k "rag"` | All pass, 0 regressions | Passed (15/15) ✅ |
| **Status Probe** | `cd backend && uv run python -c "from app.services import rag; print(rag.status())"` | `indexed: True`, `chunks: 6453` | Passed ✅ |
| **Retrieval Speed** | `cd backend && uv run python -c "import time, app.services.rag as r; t0=time.time(); r.search('asthma treatment'); print(f'Search took {time.time()-t0:.4f}s')"` | `< 50ms` (achieved 14.7ms) | Passed ✅ |

---

## 4. Definition of Done (DoD)

- [x] `backend/data/rag-index.sqlite` is generated, valid, and populated from CMDT 2026 (19 MB, 6,453 chunks).
- [x] All automated RAG tests pass via `uv run pytest tests/test_rag.py tests/test_deferred_parity.py`.
- [x] Chat query responses in the UI show grounded clinical citations from CMDT 2026.
- [x] Zero unhandled exceptions when processing special characters or empty search terms.
- [x] Excerpt prose never leaks to network payload outside prompt context.
