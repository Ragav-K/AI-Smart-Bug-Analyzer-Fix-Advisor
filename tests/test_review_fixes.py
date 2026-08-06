"""Regression tests for the Milestone 1-3 code-review fixes.

Each test pins one defect found during the review so it cannot reappear.
"""

import agents
import models
from agents.duplicate_agent import DuplicateDetectionAgent
from utils import bug_similarity, rag_search

# --- Knowledge base is reachable on a fresh clone -------------------------


def test_committed_sample_corpus_exists_and_has_text_columns():
    """The committed corpus must carry retrievable text, not only issue ids."""
    samples = sorted((bug_similarity.GITBUGS_DIR / "samples").glob("*.csv"))
    assert samples, "gitbugs/samples/ must ship with the repository"
    for path in samples:
        with path.open("r", encoding="utf-8", errors="replace", newline="") as file:
            header = file.readline().strip().split(",")
        assert bug_similarity.has_searchable_columns(header), path.name


def test_fallback_loader_reads_the_committed_samples():
    records = bug_similarity.load_bug_records()
    assert records, "the local fallback must find historical defects"
    assert any(record["summary"] for record in records)


def test_loader_skips_datasets_without_searchable_columns():
    """The *-combined.csv duplicate-id files must not become empty records."""
    assert not bug_similarity.has_searchable_columns(["Issue id", "Duplicate id"])
    assert bug_similarity.has_searchable_columns(["Issue id", "Summary"])
    assert bug_similarity.has_searchable_columns(["issue id", "description"])


def test_sample_project_name_is_derived_from_the_filename():
    from pathlib import Path

    path = Path("gitbugs/samples/cassandra_bugs_sample.csv")
    assert bug_similarity.project_name(path) == "cassandra"
    assert bug_similarity.project_name(Path("gitbugs/spark/spark_bugs.csv")) == "spark"


# --- A workflow status is never presented as a fix ------------------------


def test_workflow_status_is_not_treated_as_a_resolution():
    for status in ("Fixed", "Duplicate", "WontFix", "Works for me", "none"):
        text, recorded = rag_search.split_resolution(status)
        assert text == "", f"{status!r} must not be offered as a recommended fix"
        assert recorded == status


def test_descriptive_resolution_text_is_retained():
    resolution = "Added a null guard before dereferencing the session token."
    text, recorded = rag_search.split_resolution(resolution)
    assert text == resolution
    assert recorded == ""


def test_resolved_timestamp_column_is_not_read_as_a_resolution():
    assert "resolved" not in rag_search.FIELD_ALIASES["resolution"]


# --- Duplicate detection is not permanently silent ------------------------


def candidate(similarity, backend):
    return {
        "bug_id": "BUG-1",
        "title": "Session token is null after refresh",
        "similarity": similarity,
        "search_backend": backend,
    }


def test_fallback_backend_lowers_the_duplicate_threshold():
    agent = DuplicateDetectionAgent()
    fallback = [candidate(0.6, rag_search.FALLBACK_MODEL_NAME)]
    semantic = [candidate(0.6, rag_search.MODEL_NAME)]
    assert agent.threshold_for(fallback) == agent.FALLBACK_THRESHOLD
    assert agent.threshold_for(semantic) == agent.SEMANTIC_THRESHOLD
    assert agent.FALLBACK_THRESHOLD < agent.SEMANTIC_THRESHOLD


def test_explicit_threshold_overrides_backend_detection():
    agent = DuplicateDetectionAgent(threshold=70)
    assert agent.threshold_for([candidate(0.6, rag_search.FALLBACK_MODEL_NAME)]) == 70


def test_fallback_duplicate_is_reported_and_threshold_is_recorded():
    agent = DuplicateDetectionAgent()
    result = agent.predict(
        {
            "retrieved_bugs": [candidate(0.82, rag_search.FALLBACK_MODEL_NAME)],
            "triage": {"component": "Authentication"},
            "log_analysis": {"root_exception": "AttributeError"},
        }
    )
    assert result.threshold == agent.FALLBACK_THRESHOLD
    assert len(result.duplicates) == 1


# --- Overlapping log sources are not parsed more than once ----------------


JAVA_TRACE = (
    'java.lang.NullPointerException: Cannot invoke "User.getRole()" because "user" is null\n'
    "\tat com.app.auth.LoginService.validate(LoginService.java:52)\n"
    "\tat com.app.auth.LoginController.login(LoginController.java:18)"
)


def test_overlapping_submission_fields_do_not_duplicate_frames():
    """submitted_text is built from the other fields, so concatenating every
    source reported the same two frames five times over."""
    from agents.log_analysis_agent import LogAnalysisAgent

    submitted_text = f"Bug Description:\n{JAVA_TRACE}\n\nActual Result:\n{JAVA_TRACE}"
    result = LogAnalysisAgent().predict(
        {
            "bug_description": JAVA_TRACE,
            "actual_result": JAVA_TRACE,
            "submitted_text": submitted_text,
            "log_text": JAVA_TRACE,
        }
    )
    assert len(result.call_stack) == 2
    assert result.call_stack_summary == [
        "validate at LoginService.java:52",
        "login at LoginController.java:18",
    ]


def test_log_analysis_still_reads_each_source_on_its_own():
    from agents.log_analysis_agent import LogAnalysisAgent

    agent = LogAnalysisAgent()
    for record in (
        {"log_text": JAVA_TRACE},
        {"bug_description": JAVA_TRACE},
        {"submitted_text": JAVA_TRACE},
        JAVA_TRACE,
    ):
        assert len(agent.predict(record).call_stack) == 2


def test_genuine_recursion_frames_are_preserved():
    """Deduplication must not collapse a real recursive stack."""
    from agents.log_analysis_agent import LogAnalysisAgent

    trace = (
        "Traceback (most recent call last):\n"
        + '  File "a.py", line 3, in walk\n    walk()\n' * 4
        + "RecursionError: maximum recursion depth exceeded"
    )
    assert len(LogAnalysisAgent().predict({"log_text": trace}).call_stack) == 4


# --- Remediation degrades to diagnostics instead of going silent ----------


def test_historical_resolution_still_wins_and_is_labelled():
    """The grounded path must be unchanged and preferred."""
    from agents.remediation_agent import RemediationAgent

    resolution = "Added a null guard before dereferencing the session token."
    result = RemediationAgent().predict(
        {
            "retrieved_bugs": [{"bug_id": "H-1", "similarity": 0.9, "resolution": resolution}],
            "duplicate_detection": {"duplicates": [{"bug_id": "H-1"}]},
            "root_cause": {"root_cause": "Token was null", "confidence": 80},
            "log_analysis": {"file": "LoginService.java", "confidence": 90},
        }
    )
    assert result.basis == "historical"
    assert result.recommended_fix == resolution
    assert result.evidence_bug_ids == ["H-1"]


def test_diagnostic_fallback_recommends_a_fix_for_a_known_exception():
    """The GitBugs corpus records no fix text, so this is the common path."""
    from agents.remediation_agent import RemediationAgent

    result = RemediationAgent().predict(
        {
            "retrieved_bugs": [{"bug_id": "H-1", "similarity": 0.4}],
            "root_cause": {"root_cause": "user is null at login", "confidence": 40},
            "log_analysis": {
                "root_exception": "NullPointerException",
                "failure_point": "validate in LoginService.java",
                "file": "LoginService.java",
                "confidence": 90,
            },
        }
    )
    assert result.basis == "diagnostic"
    assert "Guard the dereferenced reference" in result.recommended_fix
    assert result.steps and result.best_practice
    assert result.evidence_bug_ids == [], "a diagnostic fix must claim no historical evidence"


def test_diagnostic_confidence_stays_below_the_historical_path():
    from agents.remediation_agent import RemediationAgent

    agent = RemediationAgent()
    log_analysis = {"root_exception": "KeyError", "confidence": 99, "file": "a.py"}
    diagnostic = agent.predict(
        {"root_cause": {"root_cause": "missing key", "confidence": 99}, "log_analysis": log_analysis}
    )
    historical = agent.predict(
        {
            "retrieved_bugs": [{"bug_id": "H-1", "similarity": 0.95, "resolution": "Used a guarded lookup for the total field."}],
            "root_cause": {"root_cause": "missing key", "confidence": 99},
            "log_analysis": log_analysis,
        }
    )
    assert diagnostic.confidence <= 55
    assert diagnostic.confidence < historical.confidence


def test_unknown_failure_still_refuses_to_recommend():
    from agents.remediation_agent import RemediationAgent

    result = RemediationAgent().predict({})
    assert result.basis == "none"
    assert result.recommended_fix.startswith("No evidence-backed")


def test_insufficient_evidence_sentinel_is_never_echoed_as_a_cause():
    from agents.remediation_agent import RemediationAgent

    result = RemediationAgent().predict(
        {
            "root_cause": {"root_cause": "Insufficient grounded evidence to determine a root cause."},
            "log_analysis": {"probable_cause": "Insufficient log context to infer a probable cause."},
        }
    )
    assert result.basis == "none"
    assert "Insufficient" not in result.recommended_fix


# --- Uploaded files are analyzed, not just stored -------------------------


def upload(path):
    import io

    class Uploaded(io.BytesIO):
        def __init__(self, source):
            super().__init__(source.read_bytes())
            self.name = source.name

    return Uploaded(path)


def sample(name):
    from pathlib import Path

    return Path(__file__).resolve().parents[1] / "sample_uploads" / name


def test_json_upload_exposes_its_embedded_stack_trace():
    """A trace inside a JSON string carries escaped newlines, which hid every
    frame from the line-anchored parsers."""
    from agents.log_analysis_agent import LogAnalysisAgent
    from utils.rag_search import extract_uploaded_text

    text = extract_uploaded_text(upload(sample("database_connection_errors.json")))
    assert "\\n" not in text, "escaped newlines must be decoded"
    result = LogAnalysisAgent().predict({"log_text": text})
    assert result.exception_type == "SQLException"
    assert len(result.call_stack) >= 3


def test_flatten_json_text_falls_back_on_invalid_json():
    from utils.rag_search import flatten_json_text

    assert flatten_json_text("{not json") == "{not json"


def test_java_caused_by_chain_reports_thrown_and_root_separately():
    from agents.log_analysis_agent import LogAnalysisAgent
    from utils.rag_search import extract_uploaded_text

    text = extract_uploaded_text(upload(sample("java_nullpointer.log")))
    result = LogAnalysisAgent().predict({"log_text": text})
    assert result.exception_type == "NullPointerException"
    assert result.root_exception == "IllegalStateException"
    # The repair pattern must still match the exception that surfaced.
    assert "null" in result.probable_cause.lower()


def test_every_sample_upload_is_extractable_and_analyzable():
    from agents.orchestrator import BugAnalysisOrchestrator
    from utils.rag_search import extract_uploaded_text

    orchestrator = BugAnalysisOrchestrator()
    files = [path for path in sample("").iterdir() if path.suffix != ".md"]
    assert files
    for path in files:
        text = extract_uploaded_text(upload(path))
        assert text.strip(), f"{path.name} produced no text"
        analysis = orchestrator.analyze({"bug_title": path.stem, "log_text": text}, path.stem)
        assert analysis["metadata"]["agent_errors"] == {}, path.name
        assert len(analysis["metadata"]["agents_executed"]) == 5, path.name


def test_structural_lines_are_not_quoted_as_the_failure():
    from utils.parser import _fallback_error_line

    assert _fallback_error_line("things happened\n}") != "}"


# --- Package exports survived the Milestone 3 merge -----------------------


def test_agents_package_exports_every_agent_and_the_orchestrator():
    assert "BugAnalysisOrchestrator" in agents.__all__
    for name in agents.__all__:
        assert hasattr(agents, name), name


def test_models_package_exports_every_contract():
    for name in ("TriageResult", "LogAnalysisResult", "RootCauseResult"):
        assert name in models.__all__
        assert hasattr(models, name)


# --- Confidence aggregation keeps its units -------------------------------


def test_overall_confidence_ignores_duplicate_similarity():
    from agents.orchestrator import BugAnalysisOrchestrator

    output = {
        "triage": {"confidence": 80},
        "log_analysis": {"confidence": 60},
        "root_cause": {},
        "remediation": {},
        "duplicate_detection": {"duplicates": [{"similarity": 10}]},
    }
    assert BugAnalysisOrchestrator._overall_confidence(output) == 70
