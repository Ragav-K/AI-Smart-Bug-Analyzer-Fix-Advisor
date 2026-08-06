"""Build the committed GitBugs sample corpus from the full local datasets.

The full GitBugs exports total roughly 491 MB and cannot be committed. This
script distils them into a small, repository-safe sample that keeps the columns
the retrieval layer actually needs, so a fresh clone has a working Historical
Defect Knowledge Base without any manual download.

Run it only when the full datasets are present locally:

    python scripts/build_sample_corpus.py
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
GITBUGS_DIR = ROOT_DIR / "gitbugs"
SAMPLE_DIR = GITBUGS_DIR / "samples"

OUTPUT_COLUMNS = ("Issue id", "Summary", "Status", "Priority", "Resolution", "Description")
MAX_DESCRIPTION_CHARS = 1200
DEFAULT_ROWS_PER_PROJECT = 400

# Row-size guard: csv rows in the source exports can exceed the default limit.
csv.field_size_limit(min(sys.maxsize, 2_147_483_647))


def source_files() -> list[Path]:
    """Return the full per-project exports, excluding the duplicate-id files."""
    return sorted(
        path
        for path in GITBUGS_DIR.glob("*/*_bugs.csv")
        if not path.stem.endswith("-combined")
    )


def distil(path: Path, row_limit: int) -> list[dict[str, str]]:
    """Read a full export and keep rows that carry usable retrieval text."""
    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8", errors="replace", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            if len(rows) >= row_limit:
                break
            summary = clean(row.get("Summary"))
            description = clean(row.get("Description"))[:MAX_DESCRIPTION_CHARS]
            # A record without any descriptive text contributes nothing to
            # retrieval and is what made the previous sample files unusable.
            if not summary and not description:
                continue
            rows.append(
                {
                    "Issue id": clean(row.get("Issue id")),
                    "Summary": summary,
                    "Status": clean(row.get("Status")),
                    "Priority": clean(row.get("Priority")),
                    "Resolution": clean(row.get("Resolution")),
                    "Description": description,
                }
            )
    return rows


def clean(value: object) -> str:
    return " ".join(str(value or "").split())


def write_sample(project: str, rows: list[dict[str, str]]) -> Path:
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    destination = SAMPLE_DIR / f"{project}_bugs_sample.csv"
    with destination.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(OUTPUT_COLUMNS))
        writer.writeheader()
        writer.writerows(rows)
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rows-per-project",
        type=int,
        default=DEFAULT_ROWS_PER_PROJECT,
        help=f"Maximum rows kept per project (default: {DEFAULT_ROWS_PER_PROJECT}).",
    )
    arguments = parser.parse_args()

    sources = source_files()
    if not sources:
        print(
            "No full GitBugs exports were found under gitbugs/. "
            "The committed sample corpus is already sufficient to run the app.",
        )
        return 1

    total = 0
    for path in sources:
        project = path.parent.name
        rows = distil(path, arguments.rows_per_project)
        if not rows:
            print(f"  skipped {project}: no rows with usable text")
            continue
        destination = write_sample(project, rows)
        total += len(rows)
        size_kb = destination.stat().st_size / 1024
        print(f"  {project}: {len(rows)} rows -> {destination.name} ({size_kb:.0f} KB)")

    print(f"Sample corpus written to {SAMPLE_DIR.relative_to(ROOT_DIR)} ({total} rows).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
