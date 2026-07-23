"""Export the log result JSON schema across Pydantic versions."""

from models.log_models import LogAnalysisResult


def get_log_schema() -> dict:
    method = getattr(LogAnalysisResult, "model_json_schema", None)
    return method() if method else LogAnalysisResult.schema()

