"""Professional structured findings dashboard for Milestone 3."""

from __future__ import annotations

from typing import Any

import streamlit as st


def render_findings_dashboard(
    analysis: dict[str, Any],
    submission: dict[str, Any] | None = None,
) -> None:
    """Render agent findings as metrics, tabs, tables, and evidence expanders."""
    submission = submission or {}
    triage = analysis.get("triage") or {}
    log_analysis = analysis.get("log_analysis") or {}
    root_cause = analysis.get("root_cause") or {}
    duplicate_detection = analysis.get("duplicate_detection") or {}
    remediation = analysis.get("remediation") or {}
    metadata = analysis.get("metadata") or {}
    if not any((triage, log_analysis, root_cause, remediation)):
        st.warning("Agent analysis is unavailable for this submission.")
        return

    st.markdown("## Structured Findings")
    severity = str(triage.get("severity") or "Unknown")
    summary_columns = st.columns(5)
    summary_columns[0].metric("Severity", severity)
    summary_columns[1].metric("Priority", triage.get("priority") or "Unknown")
    summary_columns[2].metric("Component", triage.get("component") or "Other")
    summary_columns[3].metric(
        "Overall confidence",
        f"{int(analysis.get('overall_confidence') or 0)}%",
    )
    summary_columns[4].metric(
        "Processing time",
        f"{float(metadata.get('processing_time_seconds') or 0):.2f}s",
    )
    st.progress(int(analysis.get("overall_confidence") or 0) / 100)

    # Keep every result visible in one continuous webpage. Users should not
    # need to switch tabs or download files to inspect the complete analysis.
    st.markdown("## Agent Answers")
    st.markdown("### 1. Log Analysis Agent")
    _render_log_analysis(log_analysis, _failure(metadata, "LogAnalysis"))
    st.divider()
    st.markdown("### 2. Triage Agent")
    _render_overview(submission, triage, metadata)
    st.divider()
    st.markdown("### 3. Root Cause Agent")
    _render_root_cause(root_cause, _failure(metadata, "RootCause"))
    st.divider()
    st.markdown("### 4. Duplicate Detection Agent")
    _render_duplicates(duplicate_detection, _failure(metadata, "DuplicateDetection"))
    st.divider()
    st.markdown("### 5. Remediation Agent")
    _render_remediation(remediation, _failure(metadata, "Remediation"))
    st.divider()
    st.markdown("### Complete analysis data")
    st.json(analysis)


def _failure(metadata: dict[str, Any], agent: str) -> str | None:
    """Return the recorded error for an agent that failed, if any."""
    return (metadata.get("agent_errors") or {}).get(agent)


def _render_overview(
    submission: dict[str, Any],
    triage: dict[str, Any],
    metadata: dict[str, Any],
) -> None:
    """Render submission and triage facts."""
    st.subheader(submission.get("bug_title") or "Bug overview")
    if submission.get("bug_description"):
        st.write(submission["bug_description"])
    left, right = st.columns([2, 1])
    with left:
        st.markdown("**Business impact**")
        st.write(triage.get("business_impact") or "Not determined.")
        st.info(triage.get("reasoning") or "No triage reasoning available.")
    with right:
        confidence = int(triage.get("confidence") or 0)
        st.metric("Triage confidence", f"{confidence}%")
        st.progress(confidence / 100)
    evidence = triage.get("evidence") or []
    if evidence:
        st.dataframe(
            {"Signal": evidence, "Source": ["Submitted report"] * len(evidence)},
            hide_index=True,
            use_container_width=True,
        )
    errors = metadata.get("agent_errors") or {}
    if errors:
        st.warning("Incomplete stages: " + ", ".join(errors))


def _render_log_analysis(
    log_analysis: dict[str, Any],
    failure: str | None = None,
) -> None:
    """Render normalized exception and call-stack findings."""
    if failure:
        st.error(f"Log analysis did not complete: {failure}")
        return
    if not log_analysis:
        st.info("Log analysis did not complete.")
        return
    first, second, third = st.columns(3)
    exception = log_analysis.get("root_exception") or log_analysis.get("exception_type")
    first.metric("Exception", exception or "Not detected")
    second.metric("Failure point", log_analysis.get("failure_point") or "Unknown")
    confidence = int(log_analysis.get("confidence") or 0)
    third.metric("Confidence", f"{confidence}%")
    st.progress(confidence / 100)

    thrown = log_analysis.get("exception_type")
    root = log_analysis.get("root_exception")
    if thrown and root and thrown != root:
        st.caption(
            f"{thrown} surfaced; the underlying cause was {root} from the "
            "exception chain."
        )

    st.markdown("**Stack trace summary**")
    for step in log_analysis.get("call_stack_summary") or ["No stack trace available."]:
        st.markdown(f"- {step}")
    if log_analysis.get("error_message"):
        st.error(log_analysis["error_message"])
    with st.expander("Parsed stack frames"):
        frames = log_analysis.get("call_stack") or []
        if frames:
            st.dataframe(frames, hide_index=True, use_container_width=True)
        else:
            st.caption("No complete stack frames were parsed.")


def _render_root_cause(
    root_cause: dict[str, Any],
    failure: str | None = None,
) -> None:
    """Render the grounded cause, confidence, reasoning, and evidence."""
    if failure:
        st.error(f"Root cause analysis did not complete: {failure}")
        return
    if not root_cause:
        st.info("Root cause analysis did not complete.")
        return
    confidence = int(root_cause.get("confidence") or 0)
    st.subheader("Cause")
    st.write(root_cause.get("root_cause") or "Not determined.")
    st.metric("Root cause confidence", f"{confidence}%")
    st.progress(confidence / 100)
    st.markdown("**Reasoning**")
    st.write(root_cause.get("reasoning") or "No reasoning available.")
    evidence = root_cause.get("supporting_evidence") or []
    with st.expander("Supporting evidence", expanded=True):
        if evidence:
            st.dataframe(evidence, hide_index=True, use_container_width=True)
        else:
            st.caption("No historical evidence was available.")


def _render_duplicates(
    duplicate_detection: dict[str, Any],
    failure: str | None = None,
) -> None:
    """Render a searchable high-confidence duplicate table."""
    # An agent that crashed produced no finding at all. Reporting that as
    # "no duplicate found" would present a failure as a negative result.
    if failure:
        st.error(f"Duplicate detection did not complete: {failure}")
        return
    duplicates = duplicate_detection.get("duplicates") or []
    st.caption(
        f"{int(duplicate_detection.get('candidates_evaluated') or 0)} candidates evaluated; "
        f"minimum score {int(duplicate_detection.get('threshold') or 65)}%."
    )
    if not duplicates:
        st.success("No high-confidence duplicate was found.")
        return
    ordered = ["bug_id", "similarity", "status", "summary", "resolution"]
    st.dataframe(
        duplicates,
        hide_index=True,
        use_container_width=True,
        column_order=ordered,
        column_config={
            "similarity": st.column_config.ProgressColumn(
                "Similarity",
                min_value=0,
                max_value=100,
                format="%d%%",
            )
        },
    )
    for duplicate in duplicates:
        with st.expander(f"{duplicate.get('bug_id', 'Unknown')} evidence"):
            for reason in duplicate.get("match_reasons") or []:
                st.markdown(f"- {reason}")


def _render_remediation(
    remediation: dict[str, Any],
    failure: str | None = None,
) -> None:
    """Render actionable grounded repair guidance."""
    if failure:
        st.error(f"Remediation did not complete: {failure}")
        return
    if not remediation:
        st.info("Remediation analysis did not complete.")
        return
    confidence = int(remediation.get("confidence") or 0)
    st.subheader("Recommended fix")
    basis = str(remediation.get("basis") or "historical")
    if basis == "historical":
        st.success("Grounded in the recorded resolution of a retrieved historical defect.")
    elif basis == "diagnostic":
        st.warning(
            "Inferred from the current exception and root cause. No retrieved "
            "defect recorded a resolution, so this is not historically proven."
        )
    recommendation = remediation.get("recommended_fix") or "No recommendation available."
    st.code(recommendation, language=None)
    st.caption("Use the copy control in the recommendation block to copy it.")
    st.metric("Remediation confidence", f"{confidence}%")
    st.progress(confidence / 100)
    st.markdown("**Repair steps**")
    for index, step in enumerate(remediation.get("steps") or [], start=1):
        st.markdown(f"{index}. {step}")
    files = remediation.get("files_likely_affected") or []
    if files:
        st.markdown("**Files likely affected**")
        st.code("\n".join(files), language=None)
    st.markdown("**Historical resolution**")
    st.write(remediation.get("historical_resolution") or "None recorded.")
    st.markdown("**Preventive best practice**")
    st.info(remediation.get("best_practice") or "No grounded best practice available.")


def build_markdown_report(
    analysis: dict[str, Any],
    submission: dict[str, Any] | None = None,
) -> str:
    """Create a portable, human-readable report without Streamlit state."""
    submission = submission or {}
    triage = analysis.get("triage") or {}
    log_analysis = analysis.get("log_analysis") or {}
    root_cause = analysis.get("root_cause") or {}
    duplicates = (analysis.get("duplicate_detection") or {}).get("duplicates") or []
    remediation = analysis.get("remediation") or {}
    lines = [
        "# AI Smart Bug Analysis Report",
        "",
        f"- Submission: {analysis.get('submission_id', 'Unknown')}",
        f"- Title: {submission.get('bug_title', 'Untitled')}",
        f"- Severity / Priority: {triage.get('severity', 'Unknown')} / {triage.get('priority', 'Unknown')}",
        f"- Component: {triage.get('component', 'Other')}",
        f"- Overall confidence: {analysis.get('overall_confidence', 0)}%",
        "",
        "## Log analysis",
        "",
        f"- Exception: {log_analysis.get('root_exception') or log_analysis.get('exception_type') or 'Not detected'}",
        f"- Failure point: {log_analysis.get('failure_point', 'Unknown')}",
        "",
        "## Root cause",
        "",
        str(root_cause.get("root_cause") or "Not determined."),
        "",
        str(root_cause.get("reasoning") or ""),
        "",
        "## Duplicate bugs",
        "",
    ]
    lines.extend(
        f"- {item.get('bug_id')}: {item.get('similarity')}% — {item.get('summary')}"
        for item in duplicates
    )
    if not duplicates:
        lines.append("- No high-confidence duplicate found.")
    lines.extend(
        [
            "",
            "## Recommended fix",
            "",
            str(remediation.get("recommended_fix") or "No grounded recommendation available."),
            "",
            "### Repair steps",
            "",
        ]
    )
    lines.extend(
        f"{index}. {step}"
        for index, step in enumerate(remediation.get("steps") or [], start=1)
    )
    return "\n".join(lines).strip() + "\n"
