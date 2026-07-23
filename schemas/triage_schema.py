"""Export the triage result JSON schema across Pydantic versions."""

from models.triage_models import TriageResult


def get_triage_schema() -> dict:
    method = getattr(TriageResult, "model_json_schema", None)
    return method() if method else TriageResult.schema()

