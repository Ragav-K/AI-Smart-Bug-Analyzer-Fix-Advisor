# Dataset Guide

## Supported formats

The retrieval pipeline reads:

- CSV
- JSON
- JSONL
- XLS
- XLSX

Files placed anywhere below `gitbugs/` are discovered recursively.

## Recognized fields

The normalizer accepts common aliases for:

- bug or issue ID
- title or summary
- description
- stack trace and error log
- resolution and root cause
- priority and status
- labels or component
- project or repository name

Unknown fields are ignored. Empty records are skipped, and long metadata fields
are truncated before storage.

## Repository policy

Full files matching `gitbugs/**/*_bugs.csv` are intentionally ignored because
some source datasets exceed GitHub's 100 MB per-file limit. Compact
`*-combined.csv` samples are committed so the repository remains usable after a
normal clone.

Do not force-add oversized datasets. Use one of these approaches instead:

1. Keep the raw dataset locally and document its source.
2. Commit a compact, representative sample.
3. Publish a checksum and download instructions.
4. Use an external dataset host when redistribution is permitted.

## Generated vector index

ChromaDB files are written below `data/chroma_gitbugs/`. They are derived
artifacts and are not committed. Rebuild them from the source datasets and the
locally cached `all-MiniLM-L6-v2` model.

## Licensing and privacy

Before adding a dataset:

- verify its license allows the intended use and redistribution
- retain source and attribution information
- remove credentials and personal or confidential information
- avoid committing production logs or customer reports
- document any transformation used to create a compact sample
