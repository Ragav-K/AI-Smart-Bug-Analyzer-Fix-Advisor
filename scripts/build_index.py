"""Build the Historical Defect Knowledge Base vector index.

Indexing is deliberately excluded from the interactive Streamlit path because
embedding the corpus takes minutes. Run this once before using the app to
enable semantic retrieval:

    python scripts/build_index.py

Without it, the app still works: retrieval falls back to the bounded local
token matcher, at lower recall.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from utils.rag_search import (  # noqa: E402
    INDEX_READY_MARKER,
    build_vector_database,
    get_vector_collection,
    is_vector_index_ready,
    load_historical_bugs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Discard the ready marker and re-embed every record.",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help=(
            "Also index the raw per-project exports, not just the committed "
            "sample corpus. These exceed 5 million rows in total; expect a "
            "build measured in hours and an index of tens of gigabytes."
        ),
    )
    arguments = parser.parse_args()

    if is_vector_index_ready() and not arguments.rebuild:
        print("Vector index is already built. Use --rebuild to re-embed.")
        return 0

    records = load_historical_bugs(arguments.full)
    if not records:
        print(
            "No historical defect records were found under gitbugs/.\n"
            "Verify that gitbugs/samples/ is present, or regenerate it with "
            "scripts/build_sample_corpus.py.",
        )
        return 1

    scope = "full dataset" if arguments.full else "committed sample corpus"
    print(f"Embedding {len(records)} historical defects from the {scope}.")
    if not arguments.full:
        print("Use --full to additionally index the raw per-project exports.")
    started = time.perf_counter()
    try:
        collection = get_vector_collection(build_if_missing=False)
        if arguments.rebuild:
            INDEX_READY_MARKER.unlink(missing_ok=True)
        build_vector_database(collection, arguments.full)
    except Exception as error:  # surfaced to the operator, never swallowed
        print(f"Index build failed: {type(error).__name__}: {error}")
        print(
            "The embedding model is loaded offline. If it is not cached yet, "
            "download it once with:\n"
            '  python -c "from sentence_transformers import SentenceTransformer;'
            ' SentenceTransformer(\'all-MiniLM-L6-v2\')"',
        )
        return 1

    if not is_vector_index_ready():
        print("Index build did not complete. The app will use the local fallback.")
        return 1

    elapsed = time.perf_counter() - started
    print(f"Indexed {collection.count()} records in {elapsed:.1f}s.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
