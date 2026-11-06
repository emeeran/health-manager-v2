"""Tests for local RAG service: chunking, stopwords, search ranking, and invariant."""


from app.services import insight_service, rag


def test_chunk_pages_with_overlap():
    pages = [
        (1, "A" * 1500 + "B" * 1500),  # 3000 chars -> should produce overlapping chunks
        (2, "   short text   "),  # < 80 chars -> skipped
        (3, "C" * 500),  # 500 chars -> single chunk
    ]
    chunks = rag.chunk_pages(pages, source="TestDoc", chunk_chars=2000, overlap_chars=200)
    assert len(chunks) == 3

    # Check page 1 chunks have overlap
    c1, c2 = chunks[0], chunks[1]
    assert c1["page"] == 1
    assert c2["page"] == 1
    assert c1["source"] == "TestDoc"
    assert c2["source"] == "TestDoc"
    assert len(c1["text"]) == 2000
    assert len(c2["text"]) == 1200  # remainder from 1800 stride

    # Stride of 1800 means c1[1800:2000] == c2[0:200]
    overlap_tail = c1["text"][1800:2000]
    overlap_head = c2["text"][0:200]
    assert overlap_tail == overlap_head

    # Page 3 chunk
    assert chunks[2]["page"] == 3
    assert chunks[2]["text"] == "C" * 500


def test_fts5_syntax_safety_and_stopwords(tmp_path, monkeypatch):
    monkeypatch.setattr(rag, "index_path", lambda: tmp_path / "rag.sqlite")
    monkeypatch.setattr(rag, "rag_available", lambda: True)

    pages = [
        (10, "Metformin is standard initial therapy for type 2 diabetes mellitus."),
        (20, "Hypertension guidelines recommend ACE inhibitors or ARBs."),
    ]
    rag.build_index(pages, "CMDT")

    # Conversational query with stopwords: "what", "is", "the", "for"
    hits = rag.search("what is the initial therapy for diabetes?")
    assert hits
    assert hits[0]["page"] == 10
    assert hits[0]["source"] == "CMDT"

    # Malformed FTS5 injection syntax
    injection_queries = [
        'AND OR NOT (()) "" *',
        'MATCH "nested" OR * ^ ?',
        '""""""',
        "   ",
        "??? !!! @@@ ###",
    ]
    for q in injection_queries:
        res = rag.search(q)
        assert isinstance(res, list), f"Query failed to handle cleanly: {q}"


def test_metadata_only_citations_invariant():
    citations_with_leaks = [
        {
            "source": "CMDT 2026",
            "page": 450,
            "snippet": "First-line therapy snippet...",
            "text": "Full copyrighted textbook prose that must not be sent to client...",
            "internal_score": 0.98,
        },
        {
            "source": "CMDT 2026",
            "page": 512,
            "record_id": "rec-123",
            "secret_key": "leak",
        },
    ]

    safe = insight_service.metadata_only_citations(citations_with_leaks)
    assert len(safe) == 2
    for item in safe:
        assert "text" not in item
        assert "internal_score" not in item
        assert "secret_key" not in item
        assert "source" in item
        assert "page" in item

    assert safe[1]["record_id"] == "rec-123"


def test_grounding_block_source_field(tmp_path, monkeypatch):
    monkeypatch.setattr(rag, "index_path", lambda: tmp_path / "rag.sqlite")
    monkeypatch.setattr(rag, "rag_available", lambda: True)

    pages = [(100, "Lisinopril is an ACE inhibitor used in hypertension and heart failure.")]
    rag.build_index(pages, "CMDT 2026")

    block, citations = rag.grounding_block("lisinopril indications")
    assert "CMDT 2026" in block
    assert "page 100" in block
    assert len(citations) == 1
    assert citations[0]["source"] == "CMDT 2026"
    assert citations[0]["page"] == 100
    assert "Lisinopril is an ACE inhibitor" in citations[0]["snippet"]


def test_clinical_retrieval_synthetic_benchmark(tmp_path, monkeypatch):
    monkeypatch.setattr(rag, "index_path", lambda: tmp_path / "rag.sqlite")
    monkeypatch.setattr(rag, "rag_available", lambda: True)

    pages = [
        (
            50,
            "Type 2 Diabetes Mellitus: Metformin is the preferred initial pharmacologic agent. "
            "Contraindicated in severe renal impairment with eGFR less than 30 mL/min.",
        ),
        (
            150,
            "Anaphylaxis Management: Intramuscular epinephrine 0.3 to 0.5 mg (1:1000 dilution) "
            "in the anterolateral thigh is the immediate first-line treatment of choice.",
        ),
        (
            250,
            "Hypertension Staging: Stage 2 hypertension is defined as systolic blood pressure "
            "greater than or equal to 140 mm Hg or diastolic blood pressure 90 mm Hg or higher.",
        ),
    ]
    rag.build_index(pages, "CMDT 2026")

    # Test 1: Diabetes query retrieves page 50
    t2d_hits = rag.search("what is preferred initial agent for type 2 diabetes?")
    assert t2d_hits and t2d_hits[0]["page"] == 50

    # Test 2: Anaphylaxis query retrieves page 150
    ana_hits = rag.search("emergency epinephrine dose for anaphylaxis")
    assert ana_hits and ana_hits[0]["page"] == 150

    # Test 3: Hypertension staging retrieves page 250
    htn_hits = rag.search("threshold for stage 2 hypertension diagnosis")
    assert htn_hits and htn_hits[0]["page"] == 250
