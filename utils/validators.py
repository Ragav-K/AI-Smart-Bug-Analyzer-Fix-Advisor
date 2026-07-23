from __future__ import annotations

from typing import Any


def validate_submission(record: dict[str, Any]) -> list[str]:
    """Validate the user-facing bug submission form."""
    errors: list[str] = []
    has_uploaded_files = bool(record.get("uploaded_files"))
    submission_method = str(record.get("submission_method") or "").strip()
    requires_text = submission_method in {"Text", "Text + File"}
    requires_file = submission_method in {"File", "Text + File"}

    # Preserve the previous conditional rule for callers that do not yet send a method.
    if not submission_method:
        requires_text = not has_uploaded_files

    if requires_text and not str(record.get("bug_title") or "").strip():
        errors.append("Bug Title is required.")
    if requires_text and not str(record.get("bug_description") or "").strip():
        errors.append("Bug Description is required.")
    if requires_file and not has_uploaded_files:
        errors.append("At least one supporting file is required.")

    return errors
