"""Milestone 4 end-to-end validation of the complete analysis pipeline.

This harness answers three questions the earlier agent evaluation did not:

1. **Agent accuracy** across varied bug types and stack-trace formats, measured
   on the full five-agent pipeline rather than on Triage and Log Analysis alone.
2. **Duplicate detection quality**, measured as precision, recall, and F1
   against planted ground truth: each case declares which historical defect --
   if any -- is genuinely its duplicate.
3. **Recommendation relevance**, measured as whether the remediation agent
   grounded its advice in the historical defect that actually holds the fix.

Every measurement is repeated at several **historical dataset sizes** (0, 6, 30
and 120 records) because retrieval quality, and therefore duplicate and
remediation quality, depends on how much history exists. Running with an empty
corpus also proves the pipeline degrades rather than fails.

Retrieval is performed by a deterministic in-process token matcher over a
synthetic corpus. This keeps the run reproducible and offline, and isolates
agent behaviour from embedding-model availability.

    python evaluation/end_to_end_validation.py
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from agents.orchestrator import BugAnalysisOrchestrator  # noqa: E402
from agents.pattern_analytics_agent import DefectPatternAnalyticsAgent  # noqa: E402
from utils.bug_similarity import cosine_similarity, vector_norm, vectorize  # noqa: E402
from utils.rag_search import FALLBACK_MODEL_NAME  # noqa: E402

DATASET_SIZES = (0, 6, 30, 120)


@dataclass(frozen=True)
class E2ECase:
    """One labelled submission with its expected pipeline outcome."""

    case_id: str
    bug_type: str
    trace_format: str
    submission: dict[str, Any] | str
    expected_exception: str | None
    expected_component: str | None
    expected_severity: str | None
    duplicate_of: str | None = None
    expects_stack_frames: bool = True


@dataclass
class HistoricalBug:
    """A synthetic historical defect used as retrieval ground truth."""

    bug_id: str
    title: str
    description: str
    resolution: str = ""
    root_cause: str = ""
    status: str = "Resolved"
    priority: str = "High"
    labels: str = ""

    def as_document(self) -> str:
        return " ".join(
            [self.title, self.description, self.root_cause, self.resolution, self.labels]
        )

    def as_candidate(self, similarity: float) -> dict[str, Any]:
        """Shape this bug the way the retrieval layer returns a match."""
        return {
            "bug_id": self.bug_id,
            "title": self.title,
            "description": self.description,
            "full_text": self.as_document(),
            "resolution": self.resolution,
            "root_cause": self.root_cause,
            "status": self.status,
            "priority": self.priority,
            "labels": self.labels,
            "project_name": "e2e-corpus",
            "similarity": round(similarity, 4),
            "similarity_percentage": round(similarity * 100),
            # This harness scores candidates with the same token-cosine matcher
            # the application falls back to, so it must declare that backend.
            # Claiming the embedding model would make the duplicate agent apply
            # the semantic threshold to token-scale scores and stay silent for
            # reasons that have nothing to do with the agent's quality.
            "search_backend": FALLBACK_MODEL_NAME,
            "historical_bugs_indexed": 0,
        }


JAVA_TRACE = """2026-08-05 09:14:22,502 ERROR [http-nio-8080-exec-4] LoginController - Unhandled exception
java.lang.NullPointerException: Cannot invoke "com.app.model.User.getRole()" because "user" is null
\tat com.app.auth.LoginService.validate(LoginService.java:52)
\tat com.app.auth.LoginService.authenticate(LoginService.java:34)
\tat com.app.auth.LoginController.login(LoginController.java:18)
Caused by: java.lang.IllegalStateException: Session store returned no user for token 9f3c-aa21
\tat com.app.auth.SessionStore.lookup(SessionStore.java:77)
\t... 12 more"""

PYTHON_TRACE = '''Traceback (most recent call last):
  File "/srv/api/orders.py", line 88, in create_order
    total = payload["amount"] * quantity
KeyError: 'amount' '''

NODE_TRACE = """Uncaught TypeError: Cannot read properties of undefined (reading 'amount')
    at chargeCard (/srv/payment/checkout.js:31:9)
    at processOrder (/srv/payment/order.js:77:5)
    at /srv/payment/index.js:14:3"""

SQL_TRACE = """java.sql.SQLException: Connection is not available, request timed out after 30000ms
\tat com.zaxxer.hikari.pool.HikariPool.createTimeoutException(HikariPool.java:696)
\tat com.app.repository.OrderRepository.findAll(OrderRepository.java:41)"""

PYTHON_CHAINED_TRACE = '''Traceback (most recent call last):
  File "/srv/sync/client.py", line 22, in fetch
    response = session.get(url, timeout=5)
TimeoutError: read timed out

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "/srv/sync/worker.py", line 61, in run
    self.fetch(url)
ConnectionError: upstream inventory service unreachable'''

GENERIC_TRACE = "FATAL: SecurityError: signed URL validation bypassed for tenant 41"

JSON_LOG = """level: ERROR
logger: com.app.search.IndexWriter
message: index refresh failed
stack: java.io.IOException: No space left on device
\tat com.app.search.IndexWriter.flush(IndexWriter.java:210)"""


def build_cases() -> list[E2ECase]:
    """Twelve labelled cases spanning bug types and trace formats."""
    return [
        E2ECase(
            case_id="E2E-01",
            bug_type="Authentication crash",
            trace_format="Java stack trace with Caused by",
            submission={
                "bug_title": "Login crashes for every user in production",
                "bug_description": "All users hit a 500 during login. Production outage.",
                "log_text": JAVA_TRACE,
            },
            expected_exception="IllegalStateException",
            expected_component="Authentication",
            expected_severity="Critical",
            duplicate_of="HIST-AUTH-01",
        ),
        E2ECase(
            case_id="E2E-02",
            bug_type="API payload validation",
            trace_format="Python traceback",
            submission={
                "bug_title": "Order creation fails when amount is omitted",
                "bug_description": "REST API endpoint returns 500 instead of a validation error.",
                "log_text": PYTHON_TRACE,
            },
            expected_exception="KeyError",
            expected_component="REST API",
            expected_severity=None,
            duplicate_of="HIST-API-02",
        ),
        E2ECase(
            case_id="E2E-03",
            bug_type="Payment failure",
            trace_format="Node.js stack trace",
            submission={
                "bug_title": "Checkout payment fails for all customers",
                "bug_description": "Payment gateway charge throws during checkout. Revenue impact.",
                "log_text": NODE_TRACE,
            },
            expected_exception="TypeError",
            expected_component="Payment",
            expected_severity="Critical",
            duplicate_of="HIST-PAY-03",
        ),
        E2ECase(
            case_id="E2E-04",
            bug_type="Database exhaustion",
            trace_format="Java SQL stack trace",
            submission={
                "bug_title": "Database connection pool exhausted under load",
                "bug_description": "Every SQL query times out once traffic rises.",
                "log_text": SQL_TRACE,
            },
            expected_exception="SQLException",
            expected_component="Database",
            expected_severity=None,
            duplicate_of="HIST-DB-04",
        ),
        E2ECase(
            case_id="E2E-05",
            bug_type="Upstream dependency timeout",
            trace_format="Chained Python traceback",
            submission={
                "bug_title": "Inventory sync worker stops after upstream timeout",
                "bug_description": "The sync worker dies when the inventory service is slow.",
                "log_text": PYTHON_CHAINED_TRACE,
            },
            expected_exception="ConnectionError",
            expected_component=None,
            expected_severity=None,
            duplicate_of=None,
        ),
        E2ECase(
            case_id="E2E-06",
            bug_type="Security exposure",
            trace_format="Single-line generic error",
            submission={
                "bug_title": "Signed URL validation can be bypassed",
                "bug_description": "A security vulnerability permits unauthorized access to tenant files.",
                "log_text": GENERIC_TRACE,
            },
            expected_exception="SecurityError",
            expected_component="Security",
            expected_severity="Critical",
            duplicate_of=None,
            expects_stack_frames=False,
        ),
        E2ECase(
            case_id="E2E-07",
            bug_type="Storage exhaustion",
            trace_format="Key-value log with embedded trace",
            submission={
                "bug_title": "Search index refresh fails on the primary node",
                "bug_description": "Search results go stale because the index cannot flush to disk.",
                "log_text": JSON_LOG,
            },
            expected_exception="IOException",
            expected_component="Search",
            expected_severity=None,
            duplicate_of="HIST-IDX-07",
        ),
        E2ECase(
            case_id="E2E-08",
            bug_type="Cosmetic UI defect",
            trace_format="No trace, prose only",
            submission={
                "bug_title": "Button spacing is inconsistent on the settings screen",
                "bug_description": "The Save button layout and color differ from the design system.",
                "log_text": "",
            },
            expected_exception=None,
            expected_component="UI",
            expected_severity="Low",
            duplicate_of=None,
            expects_stack_frames=False,
        ),
        E2ECase(
            case_id="E2E-09",
            bug_type="Authentication crash, re-reported",
            trace_format="Plain-text submission string",
            submission=(
                "Bug Title: Users cannot sign in\n"
                "Bug Description: Login returns a server error for everyone in production.\n"
                f"Actual Result:\n{JAVA_TRACE}"
            ),
            expected_exception="IllegalStateException",
            expected_component="Authentication",
            expected_severity=None,
            duplicate_of="HIST-AUTH-01",
        ),
        E2ECase(
            case_id="E2E-10",
            bug_type="Sparse report",
            trace_format="Minimal record, no title",
            submission={"bug_description": "Something is wrong with notifications."},
            expected_exception=None,
            expected_component="Notifications",
            expected_severity=None,
            duplicate_of=None,
            expects_stack_frames=False,
        ),
        E2ECase(
            case_id="E2E-11",
            bug_type="Empty submission",
            trace_format="Empty record",
            submission={},
            expected_exception=None,
            expected_component=None,
            expected_severity=None,
            duplicate_of=None,
            expects_stack_frames=False,
        ),
        E2ECase(
            case_id="E2E-12",
            bug_type="Very large log",
            trace_format="Java trace inside 20k lines of noise",
            submission={
                "bug_title": "Nightly batch job fails intermittently",
                "bug_description": "The batch job aborts partway through with a null reference.",
                "log_text": "\n".join(["INFO heartbeat ok"] * 20_000) + "\n" + JAVA_TRACE,
            },
            expected_exception="IllegalStateException",
            expected_component=None,
            expected_severity=None,
            duplicate_of="HIST-AUTH-01",
        ),
    ]


def build_corpus(size: int) -> list[HistoricalBug]:
    """Build a corpus of the requested size around fixed planted duplicates.

    The planted defects always come first, so growing the corpus adds
    distractors rather than changing the ground truth. That isolates the
    effect of dataset size on retrieval precision.
    """
    planted = [
        HistoricalBug(
            bug_id="HIST-AUTH-01",
            title="NullPointerException during login when the session store returns no user",
            description=(
                "Production login fails with a NullPointerException. The session store "
                "lookup returns no user for a valid token and LoginService.validate "
                "dereferences it. IllegalStateException is the underlying cause."
            ),
            resolution=(
                "Guard the session lookup in LoginService.validate and return a 401 "
                "authentication error when the session store yields no user, instead of "
                "dereferencing the null reference."
            ),
            root_cause="Session store returned no user for a valid token and the result was not checked.",
            labels="Authentication login session",
        ),
        HistoricalBug(
            bug_id="HIST-API-02",
            title="KeyError creating an order when the amount field is missing from the payload",
            description=(
                "The order creation REST API endpoint raises KeyError when the request "
                "payload omits amount, returning HTTP 500 rather than a validation error."
            ),
            resolution=(
                "Validate the order payload with a schema at the API boundary and return "
                "HTTP 400 with the missing field name instead of indexing the payload directly."
            ),
            root_cause="Request payload fields were indexed directly without validation.",
            labels="REST API endpoint request validation",
        ),
        HistoricalBug(
            bug_id="HIST-PAY-03",
            title="TypeError in the checkout payment gateway when the charge amount is undefined",
            description=(
                "Checkout fails for all customers because chargeCard reads amount from an "
                "undefined order object in the payment gateway."
            ),
            resolution=(
                "Assert the order object and its amount before calling the payment gateway, "
                "and fail the checkout with a domain error when the amount is absent."
            ),
            root_cause="The order object reached the payment gateway undefined.",
            labels="Payment checkout billing transaction",
        ),
        HistoricalBug(
            bug_id="HIST-DB-04",
            title="SQLException because the database connection pool is exhausted under load",
            description=(
                "Database queries time out after 30000ms once traffic rises because the "
                "connection pool has no available connection."
            ),
            resolution=(
                "Raise the connection pool size for peak load and close repository "
                "connections in a finally block so borrowed connections are always returned."
            ),
            root_cause="Connections were leaked by a repository method and never returned to the pool.",
            labels="Database sql connection pool",
        ),
        HistoricalBug(
            bug_id="HIST-IDX-07",
            title="IOException when the search index cannot flush because the disk is full",
            description=(
                "The search index writer fails to flush to disk with no space left on "
                "device, so search results become stale."
            ),
            resolution=(
                "Add disk headroom monitoring for the index volume and fail the refresh "
                "with an actionable alert before the device fills completely."
            ),
            root_cause="The index volume filled without any headroom alerting.",
            labels="Search index storage disk",
        ),
    ]
    if size <= len(planted):
        return planted[:size]

    distractors = [
        HistoricalBug(
            bug_id=f"HIST-NOISE-{index:03d}",
            title=f"Unrelated {topic} defect {index}",
            description=(
                f"A historical {topic} defect describing behaviour unrelated to the "
                f"submitted failures, recorded for corpus realism ({index})."
            ),
            resolution="",
            labels=topic,
            status="Closed",
            priority="Low",
        )
        for index, topic in enumerate(
            _cycle(
                [
                    "reporting export",
                    "analytics telemetry",
                    "localization",
                    "documentation",
                    "onboarding wizard",
                    "theme customisation",
                    "cache warmup",
                    "deployment pipeline",
                ],
                size - len(planted),
            ),
            start=1,
        )
    ]
    return [*planted, *distractors]


def _cycle(values: list[str], count: int) -> list[str]:
    return [values[index % len(values)] for index in range(count)]


def make_retriever(corpus: list[HistoricalBug]):
    """Return a deterministic token-similarity retriever over the corpus."""
    indexed = [
        (bug, vector := vectorize(bug.as_document()), vector_norm(vector)) for bug in corpus
    ]

    def retrieve(query: str, limit: int) -> list[dict[str, Any]]:
        query_vector = vectorize(query)
        if not query_vector or not indexed:
            return []
        query_norm = vector_norm(query_vector)
        scored = [
            (cosine_similarity(query_vector, query_norm, vector, norm), bug)
            for bug, vector, norm in indexed
        ]
        scored.sort(key=lambda item: (-item[0], item[1].bug_id))
        return [
            bug.as_candidate(similarity)
            for similarity, bug in scored[:limit]
            if similarity > 0
        ]

    return retrieve


@dataclass
class CaseOutcome:
    """Per-case measurements for one dataset size."""

    case_id: str
    bug_type: str
    trace_format: str
    dataset_size: int
    agents_executed: int
    agent_errors: dict[str, str] = field(default_factory=dict)
    predicted_exception: str | None = None
    expected_exception: str | None = None
    exception_correct: bool = False
    predicted_component: str | None = None
    expected_component: str | None = None
    component_correct: bool | None = None
    predicted_severity: str | None = None
    expected_severity: str | None = None
    severity_correct: bool | None = None
    stack_frames: int = 0
    stack_frames_expected: bool = True
    stack_parse_correct: bool = True
    expected_duplicate: str | None = None
    predicted_duplicates: list[str] = field(default_factory=list)
    duplicate_true_positive: bool = False
    duplicate_false_positive: bool = False
    duplicate_false_negative: bool = False
    remediation_basis: str = "none"
    remediation_cites_expected: bool | None = None
    recommendation_relevant: bool | None = None
    overall_confidence: int = 0
    processing_time_seconds: float = 0.0


def run_case(case: E2ECase, dataset_size: int, corpus: list[HistoricalBug]) -> tuple[CaseOutcome, dict[str, Any]]:
    """Execute one case at one dataset size and score every dimension."""
    orchestrator = BugAnalysisOrchestrator(retriever=make_retriever(corpus))
    started = time.perf_counter()
    analysis = orchestrator.analyze(case.submission, case.case_id)
    elapsed = time.perf_counter() - started

    triage = analysis.get("triage") or {}
    log_analysis = analysis.get("log_analysis") or {}
    duplicates = (analysis.get("duplicate_detection") or {}).get("duplicates") or []
    remediation = analysis.get("remediation") or {}
    metadata = analysis.get("metadata") or {}

    predicted_exception = log_analysis.get("root_exception") or log_analysis.get("exception_type")
    predicted_ids = [str(item.get("bug_id")) for item in duplicates]
    # A duplicate is only expected once the planted defect is actually in the
    # corpus. Below that size, "no duplicate" is the correct answer.
    expected_duplicate = (
        case.duplicate_of
        if case.duplicate_of and any(bug.bug_id == case.duplicate_of for bug in corpus)
        else None
    )
    frames = log_analysis.get("call_stack") or []

    outcome = CaseOutcome(
        case_id=case.case_id,
        bug_type=case.bug_type,
        trace_format=case.trace_format,
        dataset_size=dataset_size,
        agents_executed=len(metadata.get("agents_executed") or []),
        agent_errors=dict(metadata.get("agent_errors") or {}),
        predicted_exception=predicted_exception,
        expected_exception=case.expected_exception,
        exception_correct=predicted_exception == case.expected_exception,
        predicted_component=triage.get("component"),
        expected_component=case.expected_component,
        component_correct=(
            None if case.expected_component is None
            else triage.get("component") == case.expected_component
        ),
        predicted_severity=triage.get("severity"),
        expected_severity=case.expected_severity,
        severity_correct=(
            None if case.expected_severity is None
            else triage.get("severity") == case.expected_severity
        ),
        stack_frames=len(frames),
        stack_frames_expected=case.expects_stack_frames,
        stack_parse_correct=bool(frames) == case.expects_stack_frames,
        expected_duplicate=expected_duplicate,
        predicted_duplicates=predicted_ids,
        duplicate_true_positive=bool(expected_duplicate and expected_duplicate in predicted_ids),
        duplicate_false_positive=bool(
            predicted_ids and (not expected_duplicate or expected_duplicate not in predicted_ids)
        ),
        duplicate_false_negative=bool(expected_duplicate and expected_duplicate not in predicted_ids),
        remediation_basis=str(remediation.get("basis") or "none"),
        overall_confidence=int(analysis.get("overall_confidence") or 0),
        processing_time_seconds=round(elapsed, 6),
    )

    if expected_duplicate:
        cited = list(remediation.get("evidence_bug_ids") or [])
        outcome.remediation_cites_expected = expected_duplicate in cited
        # Relevance means the recommendation came from the defect that actually
        # holds the fix, not merely that some text was produced.
        outcome.recommendation_relevant = (
            outcome.remediation_cites_expected and outcome.remediation_basis == "historical"
        )
    elif dataset_size == 0:
        # With no history at all, a diagnostic recommendation is the correct
        # and most useful answer the system can give.
        outcome.recommendation_relevant = outcome.remediation_basis in {"diagnostic", "none"}

    return outcome, analysis


def summarize(outcomes: list[CaseOutcome]) -> dict[str, Any]:
    """Aggregate scored outcomes into headline quality metrics."""
    total = len(outcomes)
    if not total:
        return {}

    def rate(predicate) -> float:
        return round(sum(bool(predicate(row)) for row in outcomes) / total, 4)

    def conditional_rate(field_name: str) -> float | None:
        scored = [getattr(row, field_name) for row in outcomes if getattr(row, field_name) is not None]
        if not scored:
            return None
        return round(sum(bool(value) for value in scored) / len(scored), 4)

    true_positives = sum(row.duplicate_true_positive for row in outcomes)
    false_positives = sum(row.duplicate_false_positive for row in outcomes)
    false_negatives = sum(row.duplicate_false_negative for row in outcomes)
    precision = round(true_positives / (true_positives + false_positives), 4) if (true_positives + false_positives) else None
    recall = round(true_positives / (true_positives + false_negatives), 4) if (true_positives + false_negatives) else None
    f1 = (
        round(2 * precision * recall / (precision + recall), 4)
        if precision and recall
        else (0.0 if precision is not None and recall is not None else None)
    )

    return {
        "cases": total,
        "pipeline_completion_rate": rate(lambda row: row.agents_executed == 5),
        "cases_with_agent_errors": sum(1 for row in outcomes if row.agent_errors),
        "exception_detection_accuracy": rate(lambda row: row.exception_correct),
        "component_accuracy": conditional_rate("component_correct"),
        "severity_accuracy": conditional_rate("severity_correct"),
        "stack_parse_accuracy": rate(lambda row: row.stack_parse_correct),
        "duplicate_precision": precision,
        "duplicate_recall": recall,
        "duplicate_f1": f1,
        "duplicate_true_positives": true_positives,
        "duplicate_false_positives": false_positives,
        "duplicate_false_negatives": false_negatives,
        "recommendation_relevance": conditional_rate("recommendation_relevant"),
        "historically_grounded_share": rate(lambda row: row.remediation_basis == "historical"),
        "average_overall_confidence": round(
            statistics.mean(row.overall_confidence for row in outcomes), 2
        ),
        "average_processing_time_seconds": round(
            statistics.mean(row.processing_time_seconds for row in outcomes), 6
        ),
        "max_processing_time_seconds": round(
            max(row.processing_time_seconds for row in outcomes), 6
        ),
    }


def validate(
    output_dir: Path | None = None,
    dataset_sizes: tuple[int, ...] = DATASET_SIZES,
) -> dict[str, Any]:
    """Run every case at every dataset size and write the reports."""
    documentation_dir = (
        output_dir if output_dir is not None
        else ROOT_DIR / "Documentation" / "evaluation"
    )
    output_dir = output_dir or Path(__file__).resolve().parent
    output_dir.mkdir(parents=True, exist_ok=True)
    documentation_dir.mkdir(parents=True, exist_ok=True)

    cases = build_cases()
    all_outcomes: list[CaseOutcome] = []
    by_size: dict[str, Any] = {}
    analytics_input: list[dict[str, Any]] = []

    for size in dataset_sizes:
        corpus = build_corpus(size)
        outcomes: list[CaseOutcome] = []
        for case in cases:
            outcome, analysis = run_case(case, size, corpus)
            outcomes.append(outcome)
            if size == max(dataset_sizes):
                analytics_input.append(
                    {
                        "submission_id": case.case_id,
                        "bug_title": (
                            case.submission.get("bug_title")
                            if isinstance(case.submission, dict)
                            else case.case_id
                        )
                        or case.bug_type,
                        "timestamp": datetime.now(UTC).isoformat(),
                        "analysis": analysis,
                    }
                )
        by_size[str(size)] = summarize(outcomes)
        all_outcomes.extend(outcomes)

    analytics = DefectPatternAnalyticsAgent().predict(analytics_input).model_dump(mode="json")
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset_sizes": list(dataset_sizes),
        "case_count": len(cases),
        "total_runs": len(all_outcomes),
        "overall": summarize(all_outcomes),
        "by_dataset_size": by_size,
        "bug_types_covered": sorted({case.bug_type for case in cases}),
        "trace_formats_covered": sorted({case.trace_format for case in cases}),
        "analytics_at_largest_corpus": {
            "themes": analytics["themes"],
            "component_hotspots": analytics["component_hotspots"],
            "systemic_patterns": analytics["systemic_patterns"],
            "recurrence_rate": analytics["recurrence_rate"],
            "duplicate_rate": analytics["duplicate_rate"],
        },
    }

    (output_dir / "milestone4_e2e_report.json").write_text(
        json.dumps(
            {"summary": report, "runs": [outcome.__dict__ for outcome in all_outcomes]},
            indent=2,
        ),
        encoding="utf-8",
    )
    (documentation_dir / "milestone4_e2e_validation.md").write_text(
        build_markdown_report(report, all_outcomes), encoding="utf-8"
    )
    return report


def build_markdown_report(report: dict[str, Any], outcomes: list[CaseOutcome]) -> str:
    """Render a reviewable validation document from measured results."""

    def percent(value: Any) -> str:
        return "n/a" if value is None else f"{float(value) * 100:.2f}%"

    overall = report["overall"]
    size_rows = "\n".join(
        f"| {size} | {percent(metrics['pipeline_completion_rate'])} | "
        f"{percent(metrics['exception_detection_accuracy'])} | "
        f"{percent(metrics['duplicate_precision'])} | {percent(metrics['duplicate_recall'])} | "
        f"{percent(metrics['duplicate_f1'])} | {percent(metrics['recommendation_relevance'])} | "
        f"{percent(metrics['historically_grounded_share'])} |"
        for size, metrics in report["by_dataset_size"].items()
    )

    largest = str(max(report["dataset_sizes"]))
    case_rows = "\n".join(
        f"| `{row.case_id}` | {row.bug_type} | {row.trace_format} | "
        f"{row.predicted_exception or 'None'} | {'yes' if row.exception_correct else 'no'} | "
        f"{row.predicted_component or 'n/a'} | {row.stack_frames} | "
        f"{', '.join(row.predicted_duplicates) or 'none'} | {row.remediation_basis} |"
        for row in outcomes
        if str(row.dataset_size) == largest
    )

    failures = [
        row
        for row in outcomes
        if not row.exception_correct
        or row.component_correct is False
        or row.severity_correct is False
        or row.agents_executed != 5
        or row.recommendation_relevant is False
    ]
    failure_section = (
        "Every case completed all five agents and met its labelled expectations at every dataset size."
        if not failures
        else "\n".join(
            f"- `{row.case_id}` at corpus size {row.dataset_size}: "
            f"exception expected {row.expected_exception}, predicted {row.predicted_exception}; "
            f"component expected {row.expected_component}, predicted {row.predicted_component}; "
            f"agents executed {row.agents_executed}/5; "
            f"recommendation relevant: {row.recommendation_relevant}."
            for row in failures
        )
    )

    patterns = report["analytics_at_largest_corpus"]["systemic_patterns"]
    pattern_section = (
        "No systemic pattern crossed its detection threshold on this dataset."
        if not patterns
        else "\n".join(
            f"- **{pattern['title']}** ({pattern['affected_submissions']} submissions): {pattern['detail']}"
            for pattern in patterns
        )
    )
    theme_rows = "\n".join(
        f"| {theme['theme']} | {theme['occurrences']} | {theme['share_percentage']}% |"
        for theme in report["analytics_at_largest_corpus"]["themes"]
    )

    return f"""# Milestone 4 End-to-End Validation Report

Generated at: `{report['generated_at']}`

## Scope

{report['case_count']} labelled bug submissions were executed through the complete
five-agent pipeline at {len(report['dataset_sizes'])} historical dataset sizes
({', '.join(str(size) for size in report['dataset_sizes'])} records), for
**{report['total_runs']} total pipeline runs**.

**Bug types covered:** {', '.join(report['bug_types_covered'])}.

**Stack-trace formats covered:** {', '.join(report['trace_formats_covered'])}.

## Headline results (all runs)

| Measure | Result |
|---|---:|
| Pipeline completion (5/5 agents) | {percent(overall['pipeline_completion_rate'])} |
| Runs with an agent error | {overall['cases_with_agent_errors']} |
| Exception detection accuracy | {percent(overall['exception_detection_accuracy'])} |
| Component classification accuracy | {percent(overall['component_accuracy'])} |
| Severity classification accuracy | {percent(overall['severity_accuracy'])} |
| Stack-trace parse correctness | {percent(overall['stack_parse_accuracy'])} |
| Duplicate precision | {percent(overall['duplicate_precision'])} |
| Duplicate recall | {percent(overall['duplicate_recall'])} |
| Duplicate F1 | {percent(overall['duplicate_f1'])} |
| Recommendation relevance | {percent(overall['recommendation_relevance'])} |
| Historically grounded recommendations | {percent(overall['historically_grounded_share'])} |
| Average overall confidence | {overall['average_overall_confidence']}% |
| Average pipeline time | {overall['average_processing_time_seconds']:.6f} s |
| Slowest pipeline run | {overall['max_processing_time_seconds']:.6f} s |

## Effect of historical dataset size

| Corpus size | Pipeline completion | Exception accuracy | Duplicate precision | Duplicate recall | Duplicate F1 | Recommendation relevance | Historically grounded |
|---:|---:|---:|---:|---:|---:|---:|---:|
{size_rows}

An empty corpus is included deliberately: with no history the pipeline must
still complete, report no duplicates, and fall back to a clearly labelled
diagnostic recommendation rather than fabricating a historical one.

## Per-case results at the largest corpus

| Case | Bug type | Trace format | Exception | Correct | Component | Frames | Duplicates | Remediation basis |
|---|---|---|---|---|---|---:|---|---|
{case_rows}

## Duplicate detection quality

Ground truth is planted: each case declares the historical defect that is
genuinely its duplicate, or `None` when no true duplicate exists in the corpus.
Precision and recall are computed against that label, so a match to a plausible
but incorrect historical defect counts as a false positive.

- True positives: {overall['duplicate_true_positives']}
- False positives: {overall['duplicate_false_positives']}
- False negatives: {overall['duplicate_false_negatives']}

## Recommendation relevance

A recommendation counts as relevant only when the remediation agent grounded it
in the specific historical defect that actually records the fix
(`basis == "historical"` and the expected bug id present in `evidence_bug_ids`).
Where no history exists, a recommendation is relevant when it is correctly
labelled `diagnostic` or `none` rather than presented as historically proven.

## Defect pattern analytics on the validated corpus

| Recurring theme | Occurrences | Share |
|---|---:|---:|
{theme_rows}

{pattern_section}

## Deviations from expectation

{failure_section}

## Reproduction

```bash
python evaluation/end_to_end_validation.py
```

Artifacts:

- `Documentation/evaluation/milestone4_e2e_validation.md`
- `evaluation/milestone4_e2e_report.json`

## Limitations

Retrieval uses a deterministic token matcher over a synthetic corpus so the run
is offline and reproducible. Absolute duplicate scores therefore differ from a
semantic-index deployment, where similarity is better scaled and the duplicate
agent applies a higher threshold. The labelled expectations were authored
alongside the agent rules, so these figures characterise deterministic
in-distribution behaviour and are not an estimate of accuracy on arbitrary
production reports.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--dataset-sizes",
        type=int,
        nargs="+",
        default=list(DATASET_SIZES),
        help="Historical corpus sizes to evaluate.",
    )
    args = parser.parse_args()
    report = validate(args.output_dir, tuple(args.dataset_sizes))
    print(json.dumps(report["overall"], indent=2))


if __name__ == "__main__":
    main()
