"""The Phase-4 gate: extraction quality must stay above the F1 floor."""

from tests.extraction.evaluator import evaluate

F1_FLOOR = 0.70


async def test_extraction_quality_above_floor():
    results = await evaluate(real_ai=False)
    assert results, "evaluator returned no results"
    for result in results:
        assert result["score"]["f1"] >= F1_FLOOR, (
            f"{result['name']}: F1 {result['score']['f1']:.3f} below floor "
            f"{F1_FLOOR} — extraction regression. Full: {result['score']}"
        )


async def test_eval_is_deterministic():
    """Two runs must score identically (CI stability)."""
    first = await evaluate(real_ai=False)
    second = await evaluate(real_ai=False)
    assert [r["score"] for r in first] == [r["score"] for r in second]
