"""Local persistence and submission-form validation.

These two modules sit on either end of a submission -- validation decides
whether it may be saved, storage decides where it lands -- and both were
previously exercised only indirectly through the Streamlit page, which unit
tests cannot render. The storage tests redirect every module-level path into a
tmp_path so nothing here touches the real data/ or uploads/ directories.
"""

from __future__ import annotations

import io
import json

import pytest

from utils import storage
from utils.validators import validate_submission


class FakeUpload(io.BytesIO):
    """Minimal stand-in for Streamlit's UploadedFile."""

    def __init__(self, name: str, data: bytes) -> None:
        super().__init__(data)
        self.name = name
        self.size = len(data)


@pytest.fixture
def isolated_storage(tmp_path, monkeypatch):
    """Point every storage path at a temporary directory."""
    data_dir = tmp_path / "data"
    upload_dir = tmp_path / "uploads"
    monkeypatch.setattr(storage, "DATA_DIR", data_dir)
    monkeypatch.setattr(storage, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(storage, "LOG_DIR", upload_dir / "logs")
    monkeypatch.setattr(storage, "DOCUMENT_DIR", upload_dir / "documents")
    monkeypatch.setattr(storage, "SCREENSHOT_DIR", upload_dir / "screenshots")
    monkeypatch.setattr(storage, "REPORTS_PATH", data_dir / "bug_reports.json")
    return tmp_path


# --------------------------------------------------------------------------
# Storage
# --------------------------------------------------------------------------

def test_structure_is_created_and_starts_empty(isolated_storage):
    storage.ensure_project_structure()

    assert storage.LOG_DIR.is_dir()
    assert storage.DOCUMENT_DIR.is_dir()
    assert storage.SCREENSHOT_DIR.is_dir()
    assert storage.REPORTS_PATH.read_text(encoding="utf-8") == "[]"
    assert storage.load_reports() == []


def test_saved_reports_round_trip(isolated_storage):
    storage.save_report({"submission_id": "BUG-1", "bug_title": "崩溃 🐛"})
    storage.save_report({"submission_id": "BUG-2"})

    reports = storage.load_reports()
    assert [report["submission_id"] for report in reports] == ["BUG-1", "BUG-2"]
    # Unicode must survive the write, not be escaped into \u sequences.
    assert reports[0]["bug_title"] == "崩溃 🐛"


def test_corrupt_report_store_is_tolerated(isolated_storage):
    storage.ensure_project_structure()
    storage.REPORTS_PATH.write_text("{not valid json", encoding="utf-8")

    # A hand-edited or half-written file must not break the whole page.
    assert storage.load_reports() == []


def test_update_report_merges_fields_and_reports_a_miss(isolated_storage):
    storage.save_report({"submission_id": "BUG-1", "status": "New"})

    assert storage.update_report("BUG-1", {"status": "Resolved", "owner": "qa"}) is True
    assert storage.update_report("BUG-404", {"status": "Resolved"}) is False

    saved = storage.load_reports()[0]
    assert saved["status"] == "Resolved"
    assert saved["owner"] == "qa"


def test_submission_ids_increment_within_a_day(isolated_storage):
    first = storage.generate_submission_id()
    storage.save_report({"submission_id": first})
    second = storage.generate_submission_id()

    assert first.endswith("-001")
    assert second.endswith("-002")
    assert first.startswith("BUG-")


def test_uploads_are_routed_by_extension(isolated_storage):
    storage.ensure_project_structure()

    log = storage.save_uploaded_file(FakeUpload("trace.log", b"NullPointerException"), "BUG-1")
    document = storage.save_uploaded_file(FakeUpload("report.pdf", b"%PDF-1.4"), "BUG-1")
    shot = storage.save_uploaded_file(FakeUpload("shot.png", b"\x89PNG"), "BUG-1", is_screenshot=True)

    assert storage.LOG_DIR in (storage.LOG_DIR / log["stored_name"]).parents
    assert log["path"].endswith("BUG-1_trace.log")
    assert document["path"].endswith("BUG-1_report.pdf")
    assert "screenshots" in shot["path"]
    assert log["size_bytes"] == len(b"NullPointerException")
    assert log["extension"] == ".log"


def test_same_filename_twice_does_not_overwrite(isolated_storage):
    storage.ensure_project_structure()

    first = storage.save_uploaded_file(FakeUpload("trace.log", b"first"), "BUG-1")
    second = storage.save_uploaded_file(FakeUpload("trace.log", b"second"), "BUG-1")

    assert first["stored_name"] != second["stored_name"]
    assert (storage.LOG_DIR / first["stored_name"]).read_bytes() == b"first"
    assert (storage.LOG_DIR / second["stored_name"]).read_bytes() == b"second"


def test_traversal_filename_is_written_inside_the_upload_directory(isolated_storage):
    storage.ensure_project_structure()

    saved = storage.save_uploaded_file(FakeUpload("../../../evil.log", b"pwned"), "BUG-1")

    written = storage.LOG_DIR / saved["stored_name"]
    assert written.is_file()
    assert storage.LOG_DIR in written.parents


def test_report_store_stays_valid_json_after_an_upload_cycle(isolated_storage):
    storage.ensure_project_structure()
    metadata = storage.save_uploaded_file(FakeUpload("a.log", b"x"), "BUG-1")
    storage.save_report({"submission_id": "BUG-1", "uploaded_files": [metadata]})

    parsed = json.loads(storage.REPORTS_PATH.read_text(encoding="utf-8"))
    assert parsed[0]["uploaded_files"][0]["filename"] == "a.log"


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

def test_text_submission_requires_title_and_description():
    errors = validate_submission({"submission_method": "Text"})

    assert "Bug Title is required." in errors
    assert "Bug Description is required." in errors


def test_file_submission_requires_a_file_but_not_text():
    errors = validate_submission({"submission_method": "File"})

    assert errors == ["At least one supporting file is required."]


def test_combined_submission_requires_both():
    errors = validate_submission({"submission_method": "Text + File", "bug_title": "Crash"})

    assert "Bug Description is required." in errors
    assert "At least one supporting file is required." in errors
    assert "Bug Title is required." not in errors


def test_complete_submissions_produce_no_errors():
    assert validate_submission({
        "submission_method": "Text",
        "bug_title": "Crash on login",
        "bug_description": "NullPointerException when submitting",
    }) == []
    assert validate_submission({
        "submission_method": "File",
        "uploaded_files": [FakeUpload("a.log", b"x")],
    }) == []


def test_whitespace_only_text_does_not_satisfy_a_required_field():
    errors = validate_submission({
        "submission_method": "Text",
        "bug_title": "   ",
        "bug_description": "\n\t ",
    })

    assert len(errors) == 2


def test_legacy_callers_without_a_method_fall_back_to_the_old_rule():
    """Older callers omit submission_method; a file alone was accepted then."""
    assert validate_submission({"uploaded_files": [FakeUpload("a.log", b"x")]}) == []

    errors = validate_submission({})
    assert "Bug Title is required." in errors
    assert "Bug Description is required." in errors
