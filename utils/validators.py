from __future__ import annotations

from typing import Any


def validate_submission(record: dict[str, Any]) -> list[str]:
    """Validate the user-facing bug submission form."""
    errors: list[str] = []

    if not record.get("project_name", "").strip():
        errors.append("Project Name is required.")
    if not record.get("bug_title", "").strip():
        errors.append("Bug Title is required.")
    if not record.get("bug_description", "").strip():
        errors.append("Bug Description is required.")

    has_evidence = any(
        [
            record.get("stack_trace", "").strip(),
            record.get("error_logs", "").strip(),
            record.get("uploaded_files"),
            record.get("screenshot"),
        ]
    )
    if not has_evidence:
        errors.append(
            "Add at least one evidence item: Stack Trace, Error Log, Uploaded File, or Screenshot."
        )

    return errors
