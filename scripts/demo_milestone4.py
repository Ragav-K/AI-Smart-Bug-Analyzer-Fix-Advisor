"""Milestone 4 demonstration: five bug submissions, end to end.

Runs five distinct defects through the complete five-agent pipeline, then
demonstrates the two Milestone 4 capabilities on top of it:

1. **Knowledge base growth** -- the confirmed fix for the first defect is
   written back, and the fifth defect (a re-report of the same failure) is
   re-analyzed to show its recommendation move from an inferred diagnostic to
   an evidence-backed historical fix.
2. **Defect pattern analytics** -- recurring themes, component hotspots, and
   systemic patterns measured across all five submissions.

    python scripts/demo_milestone4.py
    python scripts/demo_milestone4.py --cleanup   # undo the knowledge base write

The demo writes `evaluation/milestone4_demo_report.md` and prints a transcript.
It does not touch `data/bug_reports.json`.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from agents.orchestrator import BugAnalysisOrchestrator  # noqa: E402
from agents.pattern_analytics_agent import DefectPatternAnalyticsAgent  # noqa: E402
from ui.findings import build_markdown_report  # noqa: E402
from utils import knowledge_base  # noqa: E402
from utils.rag_search import (  # noqa: E402
    get_vector_collection,
    is_vector_index_ready,
    load_embedding_model,
)

REPORT_PATH = ROOT_DIR / "evaluation" / "milestone4_demo_report.md"

JAVA_LOGIN_TRACE = """2026-08-05 09:14:22,502 ERROR [http-nio-8080-exec-4] LoginController - Unhandled exception during login
java.lang.NullPointerException: Cannot invoke "com.app.model.User.getRole()" because "user" is null
\tat com.app.auth.LoginService.validate(LoginService.java:52)
\tat com.app.auth.LoginService.authenticate(LoginService.java:34)
\tat com.app.auth.LoginController.login(LoginController.java:18)
Caused by: java.lang.IllegalStateException: Session store returned no user for token 9f3c-aa21
\tat com.app.auth.SessionStore.lookup(SessionStore.java:77)
\t... 12 more"""

SUBMISSIONS: list[dict[str, Any]] = [
    {
        "submission_id": "DEMO-001",
        "bug_title": "Login crashes for every user in production",
        "bug_description": (
            "Production outage: all users receive HTTP 500 when signing in. "
            "Authentication is completely broken."
        ),
        "steps_to_reproduce": "1. Open the login page\n2. Enter valid credentials\n3. Submit",
        "expected_result": "The user is signed in and redirected to the dashboard.",
        "actual_result": "The request fails with a server error.",
        "environment": "Production, Java 17, Spring Boot 3.2",
        "log_text": JAVA_LOGIN_TRACE,
    },
    {
        "submission_id": "DEMO-002",
        "bug_title": "Order creation returns 500 when the amount field is missing",
        "bug_description": (
            "The REST API endpoint for order creation raises an unhandled error "
            "instead of a validation response when the request omits amount."
        ),
        "steps_to_reproduce": "1. POST /api/orders without an amount field",
        "expected_result": "HTTP 400 naming the missing field.",
        "actual_result": "HTTP 500 with a stack trace.",
        "environment": "Staging, Python 3.11, FastAPI",
        "log_text": '''Traceback (most recent call last):
  File "/srv/api/orders.py", line 88, in create_order
    total = payload["amount"] * quantity
KeyError: 'amount' ''',
    },
    {
        "submission_id": "DEMO-003",
        "bug_title": "Checkout payment fails for all customers",
        "bug_description": (
            "Payment fails at the gateway during checkout for every customer. "
            "Revenue impact is immediate."
        ),
        "steps_to_reproduce": "1. Add an item to the cart\n2. Proceed to checkout\n3. Pay by card",
        "expected_result": "The card is charged and the order is confirmed.",
        "actual_result": "Checkout aborts with a client-side error.",
        "environment": "Production, Node.js 20",
        "log_text": """Uncaught TypeError: Cannot read properties of undefined (reading 'amount')
    at chargeCard (/srv/payment/checkout.js:31:9)
    at processOrder (/srv/payment/order.js:77:5)
    at /srv/payment/index.js:14:3""",
    },
    {
        "submission_id": "DEMO-004",
        "bug_title": "Database connection pool exhausted under load",
        "bug_description": (
            "Every SQL query times out once traffic rises. The database becomes "
            "unavailable to the reporting workflow."
        ),
        "steps_to_reproduce": "1. Drive 200 concurrent requests at the orders report",
        "expected_result": "Reports render within two seconds.",
        "actual_result": "Requests hang, then fail after 30 seconds.",
        "environment": "Production, PostgreSQL 15, HikariCP",
        "log_text": """java.sql.SQLException: Connection is not available, request timed out after 30000ms
\tat com.zaxxer.hikari.pool.HikariPool.createTimeoutException(HikariPool.java:696)
\tat com.app.repository.OrderRepository.findAll(OrderRepository.java:41)""",
    },
    {
        "submission_id": "DEMO-005",
        "bug_title": "Users cannot sign in after the evening deployment",
        "bug_description": (
            "Reported separately by support: sign-in fails for all users with a "
            "server error. Same symptom as the earlier production outage."
        ),
        "steps_to_reproduce": "1. Attempt to sign in with any account",
        "expected_result": "Sign-in succeeds.",
        "actual_result": "A server error is returned.",
        "environment": "Production, Java 17",
        "log_text": JAVA_LOGIN_TRACE,
    },
]

CONFIRMED_FIX = (
    "Guard the session lookup in LoginService.validate: when SessionStore.lookup returns "
    "no user for a token, return a 401 authentication failure instead of dereferencing "
    "the null reference, and cover the missing-session path with a regression test."
)


def analyze_all(orchestrator: BugAnalysisOrchestrator) -> list[dict[str, Any]]:
    """Run the five-agent pipeline over every demo submission."""
    records = []
    for submission in SUBMISSIONS:
        record = dict(submission)
        record["timestamp"] = datetime.now(UTC).isoformat(timespec="seconds")
        record["analysis"] = orchestrator.analyze(record, record["submission_id"])
        records.append(record)
    return records


def describe(record: dict[str, Any]) -> str:
    """Summarize one submission's full pipeline output as one line per agent."""
    analysis = record["analysis"]
    triage = analysis.get("triage") or {}
    log_analysis = analysis.get("log_analysis") or {}
    root_cause = analysis.get("root_cause") or {}
    duplicates = (analysis.get("duplicate_detection") or {}).get("duplicates") or []
    remediation = analysis.get("remediation") or {}
    duplicate_text = (
        ", ".join(f"{item['bug_id']} ({item['similarity']}%)" for item in duplicates)
        or "none above threshold"
    )
    return "\n".join(
        [
            f"### {record['submission_id']} — {record['bug_title']}",
            "",
            f"- **Log Analysis:** {log_analysis.get('language')} log, "
            f"{log_analysis.get('root_exception') or log_analysis.get('exception_type') or 'no exception'} "
            f"at {log_analysis.get('failure_point')} ({log_analysis.get('confidence')}% confidence)",
            f"- **Triage:** {triage.get('severity')} / {triage.get('priority')} / "
            f"{triage.get('component')} ({triage.get('confidence')}% confidence)",
            f"- **Root Cause:** {root_cause.get('root_cause')} ({root_cause.get('confidence')}% confidence)",
            f"- **Duplicates:** {duplicate_text}",
            f"- **Remediation ({remediation.get('basis')}, {remediation.get('confidence')}% confidence):** "
            f"{remediation.get('recommended_fix')}",
            f"- **Overall confidence:** {analysis.get('overall_confidence')}% in "
            f"{(analysis.get('metadata') or {}).get('processing_time_seconds')}s",
            "",
        ]
    )


def cleanup() -> int:
    """Remove the entries this demo added to the knowledge base.

    Removal covers the vector index as well as the CSV, so a repeated demo
    starts from a genuinely clean knowledge base and the before/after growth
    comparison stays meaningful.
    """
    removed = 0
    unindexed = 0
    for submission in SUBMISSIONS:
        result = knowledge_base.remove_confirmed_fix(submission["submission_id"])
        removed += result["removed"]
        unindexed += int(result["unindexed"])
    print(f"Removed {removed} demo entry(ies) from the knowledge base ({unindexed} un-indexed).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Remove the demo's knowledge base entries and exit.",
    )
    arguments = parser.parse_args()
    if arguments.cleanup:
        return cleanup()

    # Load the embedding model before timing anything. Cold, it takes about 25
    # seconds -- far beyond the retrieval timeout -- so without this the first
    # submission would quietly fall back to the lexical matcher and the demo
    # would understate its own retrieval quality.
    if is_vector_index_ready():
        print("Loading the embedding model (roughly 25s on a cold start)...")
        load_embedding_model()
        get_vector_collection(build_if_missing=False)
        print("Semantic retrieval ready.")
    else:
        print(
            "No vector index found; retrieval will use the local token matcher.\n"
            "Build it first for the full demonstration:  python scripts/build_index.py"
        )

    orchestrator = BugAnalysisOrchestrator()
    print("Running the five-agent pipeline over 5 distinct submissions...")
    records = analyze_all(orchestrator)
    for record in records:
        print(describe(record))

    # --- Knowledge base growth -------------------------------------------
    before = records[-1]["analysis"]
    before_basis = (before.get("remediation") or {}).get("basis")
    before_duplicates = len((before.get("duplicate_detection") or {}).get("duplicates") or [])

    print("Confirming the fix for DEMO-001 and feeding it back into the knowledge base...")
    outcome = knowledge_base.record_confirmed_fix(
        records[0], CONFIRMED_FIX, confirmed_by="Demo reviewer"
    )
    print(
        f"  Stored as {outcome['record']['Issue id']}; the knowledge base now holds "
        f"{outcome['entries']} confirmed fix(es); "
        f"indexed immediately: {outcome['indexed_immediately']}."
    )

    print("Re-analyzing DEMO-005, the re-report of the same failure...")
    after_record = dict(SUBMISSIONS[-1])
    after_record["timestamp"] = datetime.now(UTC).isoformat(timespec="seconds")
    after_record["analysis"] = orchestrator.analyze(after_record, "DEMO-005-RERUN")
    after = after_record["analysis"]
    after_basis = (after.get("remediation") or {}).get("basis")
    after_duplicates = (after.get("duplicate_detection") or {}).get("duplicates") or []
    print(f"  Remediation basis: {before_basis} -> {after_basis}")
    print(f"  Duplicates found: {before_duplicates} -> {len(after_duplicates)}")

    # --- Defect pattern analytics ----------------------------------------
    analytics = DefectPatternAnalyticsAgent().predict(records)
    print(
        f"Analytics: {len(analytics.themes)} theme(s), "
        f"{len(analytics.component_hotspots)} hotspot(s), "
        f"{len(analytics.systemic_patterns)} systemic pattern(s), "
        f"recurrence {analytics.recurrence_rate}%."
    )

    REPORT_PATH.write_text(
        build_demo_report(records, analytics, before, after, outcome, after_duplicates),
        encoding="utf-8",
    )
    print(f"\nWrote {REPORT_PATH.relative_to(ROOT_DIR)}")
    print("Undo the knowledge base write with: python scripts/demo_milestone4.py --cleanup")
    return 0


def build_demo_report(
    records: list[dict[str, Any]],
    analytics: Any,
    before: dict[str, Any],
    after: dict[str, Any],
    outcome: dict[str, Any],
    after_duplicates: list[dict[str, Any]],
) -> str:
    """Render the demonstration transcript as a reviewable document."""
    data = analytics.model_dump(mode="json")
    theme_rows = "\n".join(
        f"| {theme['theme']} | {theme['occurrences']} | {theme['share_percentage']}% | "
        f"{', '.join(theme['example_submission_ids'])} |"
        for theme in data["themes"]
    )
    hotspot_rows = "\n".join(
        f"| {hotspot['component']} | {hotspot['defect_count']} | {hotspot['share_percentage']}% | "
        f"{hotspot['high_impact_count']} | {', '.join(hotspot['top_exceptions']) or 'n/a'} |"
        for hotspot in data["component_hotspots"]
    )
    pattern_section = (
        "No systemic pattern crossed its detection threshold on these five submissions."
        if not data["systemic_patterns"]
        else "\n\n".join(
            f"**{pattern['title']}** ({pattern['affected_submissions']} submissions)\n\n"
            f"{pattern['detail']}\n\n"
            + "\n".join(f"- {item}" for item in pattern["evidence"])
            + f"\n\n*Recommendation:* {pattern['recommendation']}"
            for pattern in data["systemic_patterns"]
        )
    )
    before_remediation = before.get("remediation") or {}
    after_remediation = after.get("remediation") or {}
    duplicate_text = (
        ", ".join(f"{item['bug_id']} ({item['similarity']}%)" for item in after_duplicates)
        or "none"
    )

    return f"""# Milestone 4 Demonstration

Generated at: `{datetime.now(UTC).isoformat()}`

Five distinct bug submissions were processed by the complete five-agent
pipeline, followed by a knowledge base growth demonstration and defect pattern
analytics across all five.

## 1. Full agent pipeline output

{"".join(describe(record) for record in records)}

## 2. Knowledge base growth

The confirmed fix for `DEMO-001` was written back to the Historical Defect
Knowledge Base as `{outcome['record']['Issue id']}`:

> {outcome['record']['Resolution']}

`DEMO-005` reports the same failure. It was then re-analyzed with the knowledge
base grown by exactly that one confirmed fix.

| Measure | Before the confirmed fix | After |
|---|---|---|
| Remediation basis | `{before_remediation.get('basis')}` | `{after_remediation.get('basis')}` |
| Remediation confidence | {before_remediation.get('confidence')}% | {after_remediation.get('confidence')}% |
| Duplicates detected | {len((before.get('duplicate_detection') or {}).get('duplicates') or [])} | {duplicate_text} |
| Evidence bug ids | {', '.join(before_remediation.get('evidence_bug_ids') or []) or 'none'} | {', '.join(after_remediation.get('evidence_bug_ids') or []) or 'none'} |

**Recommendation after growth:**

> {after_remediation.get('recommended_fix')}

## 3. Defect pattern analytics

- Submissions analyzed: {data['submissions_with_pipeline_output']}
- Recurrence rate: {data['recurrence_rate']}%
- Duplicate rate: {data['duplicate_rate']}%
- Confirmed fixes in the knowledge base: {data['knowledge_base_entries']}

### Recurring themes

| Theme | Occurrences | Share | Submissions |
|---|---:|---:|---|
{theme_rows}

### High-frequency affected components

| Component | Defects | Share | Critical/High | Top exceptions |
|---|---:|---:|---:|---|
{hotspot_rows}

### Systemic issue patterns

{pattern_section}

## 4. Full structured report for the first submission

{build_markdown_report(records[0]['analysis'], records[0])}

## Reproduction

```bash
python scripts/demo_milestone4.py
```

Undo the knowledge base write with:

```bash
python scripts/demo_milestone4.py --cleanup
```
"""


if __name__ == "__main__":
    raise SystemExit(main())
