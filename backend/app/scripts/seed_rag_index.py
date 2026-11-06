"""Seed the local RAG index from your own medical reference PDF.

    uv run python -m app.scripts.seed_rag_index /path/to/reference.pdf

The index stays on this machine — copyrighted text is never distributed.
"""

import argparse
import sys
from pathlib import Path

import fitz


def pdf_pages(path: str) -> list[tuple[int, str]]:
    pages = []
    with fitz.open(path) as doc:
        total = doc.page_count
        for n in range(total):
            if (n + 1) % 100 == 0 or n + 1 == total:
                print(f"Extracting pages: {n + 1}/{total}...", flush=True)
            text = doc[n].get_text()
            if text.strip():
                pages.append((n + 1, text))
    return pages


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", help="Path to the reference PDF")
    parser.add_argument(
        "--source-name", default=None, help="Citation source name (default: file stem)"
    )
    args = parser.parse_args()

    from app.services import rag

    pages = pdf_pages(args.pdf)
    if not pages:
        print("No extractable text — is this a scanned PDF?", file=sys.stderr)
        sys.exit(2)
    source = args.source_name or Path(args.pdf).stem
    count = rag.build_index(pages, source)
    print(f"Indexed {count} chunks from {len(pages)} pages → {rag.index_path()}")


if __name__ == "__main__":
    main()
