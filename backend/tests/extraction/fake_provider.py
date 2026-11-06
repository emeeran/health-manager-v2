"""Deterministic fake provider for eval/CI — replies by document name."""

from tests.extraction.golden_documents import GOLDEN_DOCUMENTS


class FakeExtractionProvider:
    name = "fake"
    model = "canned"
    local = True
    timeout = 1

    async def available(self) -> bool:
        return True

    # Distinctive tokens per document (PDF text extraction normalizes
    # whitespace, so prefix matching is unreliable).
    MARKERS = {
        "cbc_metabolic_panel": "greenvalley",
        "diabetes_prescription": "city care clinic",
    }

    async def complete(self, prompt: str, **kwargs) -> str:
        lowered = prompt.lower()
        for doc in GOLDEN_DOCUMENTS:
            marker = self.MARKERS[doc["name"]]
            if marker in lowered:
                return doc["fake_reply"]
        raise AssertionError("FakeExtractionProvider got an unknown document")
