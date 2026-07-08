from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from streamlit.runtime.uploaded_file_manager import UploadedFile


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
UPLOAD_DIR = ROOT_DIR / "uploads"
LOG_DIR = UPLOAD_DIR / "logs"
DOCUMENT_DIR = UPLOAD_DIR / "documents"
SCREENSHOT_DIR = UPLOAD_DIR / "screenshots"
REPORTS_PATH = DATA_DIR / "bug_reports.json"


def ensure_project_structure() -> None:
    """Create folders and the JSON file required for local storage."""
    for path in [DATA_DIR, LOG_DIR, DOCUMENT_DIR, SCREENSHOT_DIR]:
        path.mkdir(parents=True, exist_ok=True)
    if not REPORTS_PATH.exists():
        REPORTS_PATH.write_text("[]", encoding="utf-8")


def load_reports() -> list[dict[str, Any]]:
    """Read all saved reports from local JSON storage."""
    ensure_project_structure()
    try:
        return json.loads(REPORTS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def save_report(record: dict[str, Any]) -> None:
    """Persist a report to the local JSON store."""
    reports = load_reports()
    reports.append(record)
    REPORTS_PATH.write_text(
        json.dumps(reports, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def generate_submission_id() -> str:
    """Generate an ID in the format BUG-YYYYMMDD-001."""
    today = datetime.now().strftime("%Y%m%d")
    reports = load_reports()
    todays_count = sum(
        1
        for report in reports
        if str(report.get("submission_id", "")).startswith(f"BUG-{today}-")
    )
    return f"BUG-{today}-{todays_count + 1:03d}"


def sanitize_filename(filename: str) -> str:
    """Keep filenames portable and safe for local storage."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", filename.strip())
    return cleaned or "uploaded_file"


def destination_for_file(uploaded_file: UploadedFile, is_screenshot: bool = False) -> Path:
    """Choose the correct storage folder for an uploaded file."""
    if is_screenshot:
        return SCREENSHOT_DIR

    suffix = Path(uploaded_file.name).suffix.lower()
    if suffix in {".txt", ".log"}:
        return LOG_DIR
    return DOCUMENT_DIR


def save_uploaded_file(
    uploaded_file: UploadedFile,
    submission_id: str,
    is_screenshot: bool = False,
) -> dict[str, Any]:
    """Save an uploaded file and return metadata for the report record."""
    ensure_project_structure()
    safe_name = sanitize_filename(uploaded_file.name)
    destination = destination_for_file(uploaded_file, is_screenshot)
    saved_path = destination / f"{submission_id}_{safe_name}"

    saved_path.write_bytes(uploaded_file.getbuffer())
    stat = saved_path.stat()

    return {
        "filename": uploaded_file.name,
        "stored_name": saved_path.name,
        "extension": saved_path.suffix.lower() or "No extension",
        "size_bytes": stat.st_size,
        "path": str(saved_path),
        "upload_time": datetime.now().isoformat(timespec="seconds"),
    }
