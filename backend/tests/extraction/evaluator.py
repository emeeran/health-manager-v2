"""Extraction evaluation harness.

CI mode (default): scores the deterministic fake provider — fast, offline,
stable. Scores must stay above the F1 gate or extraction regressions are
suspect.

--real-ai: runs against live providers (Ollama expected on the host);
scores printed for eyeballing, never asserted.

Usage:  uv run python -m tests.extraction.evaluator [--real-ai] [--json]
"""

import argparse
import asyncio
import json
import sys

import fitz


def text_to_pdf_bytes(text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text, fontsize=10)
    data = doc.tobytes()
    doc.close()
    return data


def _png_bytes() -> bytes:
    # 1x1 PNG, for the (unexercised here) image path.
    return bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000d4944415478da63fcffff3f030005fe02fea72d1e480000000049454e44ae426082"
    )


async def evaluate(real_ai: bool = False) -> list[dict]:
    from tests.extraction.fake_provider import FakeExtractionProvider
    from tests.extraction.golden_documents import GOLDEN_DOCUMENTS
    from tests.extraction.metrics import score

    if real_ai:
        from app.services.ai import router as ai_router

        provider = await ai_router.first_available(ai_router.build_plan())
        if provider is None:
            print("No AI provider available — is Ollama up?", file=sys.stderr)
            sys.exit(2)
    else:
        provider = FakeExtractionProvider()

    from app.services.ai.extraction import run_extraction

    results = []
    for doc in GOLDEN_DOCUMENTS:
        data = text_to_pdf_bytes(doc["text"])
        result = await run_extraction(data, doc["mime"], provider)
        results.append(
            {
                "name": doc["name"],
                "provider": result.provider_used,
                "score": score(doc["expected"], result.clinical_data),
                "clinical_data": result.clinical_data,
            }
        )
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--real-ai", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    results = asyncio.run(evaluate(real_ai=args.real_ai))
    if args.as_json:
        print(json.dumps(results, indent=2, default=str))
        return

    print(f"{'document':<28} {'precision':>9} {'recall':>8} {'f1':>7}")
    for r in results:
        s = r["score"]
        print(f"{r['name']:<28} {s['precision']:>9.3f} {s['recall']:>8.3f} {s['f1']:>7.3f}")
    aggregate_f1 = sum(r["score"]["f1"] for r in results) / len(results)
    print(f"\naggregate F1: {aggregate_f1:.3f}  (provider: {results[0]['provider']})")


if __name__ == "__main__":
    main()
