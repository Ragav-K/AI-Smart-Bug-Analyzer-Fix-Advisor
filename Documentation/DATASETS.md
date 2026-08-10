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

Full files matching `gitbugs/*/*_bugs.csv` are intentionally ignored because the
complete exports total roughly 491 MB and some individual files exceed GitHub's
100 MB per-file limit.

The committed knowledge base is `gitbugs/samples/` (9 projects, 400 rows each,
about 2.5 MB), which carries the `Summary`, `Status`, `Priority`, `Resolution`,
and `Description` columns that retrieval needs. Regenerate it from the full
exports with:

```bash
python scripts/build_sample_corpus.py
```

The `*-combined.csv` files hold only `Issue id` and duplicate-id columns. They
are the GitBugs duplicate ground truth, not a usable corpus, and both loaders
skip any dataset without a `Summary` or `Description` column.

Do not force-add oversized datasets. Use one of these approaches instead:

1. Keep the raw dataset locally and document its source.
2. Commit a compact, representative sample.
3. Publish a checksum and download instructions.
4. Use an external dataset host when redistribution is permitted.

## Generated vector index

ChromaDB files are written below `data/chroma_gitbugs/`. They are derived
artifacts and are not committed. Build them once with:

```bash
python scripts/build_index.py
```

This embeds the corpus with the locally cached `all-MiniLM-L6-v2` model and
writes a `.index_ready` marker. Until it exists, the app runs on the bounded
local token matcher at lower recall, which it reports in the UI.

### Resolution columns

Issue trackers record a one-word workflow outcome (`Fixed`, `Duplicate`,
`WontFix`) in their `Resolution` column. That states a defect was closed, not
how it was repaired, so the normalizer routes such values to
`resolution_status` and keeps only descriptive text as `resolution`. This stops
the remediation agent from presenting the word "Fixed" as a recommended fix.

## Licensing and privacy

Before adding a dataset:

- verify its license allows the intended use and redistribution
- retain source and attribution information
- remove credentials and personal or confidential information
- avoid committing production logs or customer reports
- document any transformation used to create a compact sample
