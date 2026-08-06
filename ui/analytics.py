"""Milestone 4 UI: defect pattern analytics and knowledge base growth."""

from __future__ import annotations

from typing import Any

import streamlit as st

from utils.knowledge_base import (
    ConfirmedFixError,
    is_learned,
    learned_entry_count,
    record_confirmed_fix,
)
from utils.storage import update_report


def render_analytics_dashboard(reports: list[dict[str, Any]]) -> None:
    """Render recurring themes, component hotspots, and systemic patterns."""
    from agents.pattern_analytics_agent import DefectPatternAnalyticsAgent

    analytics = DefectPatternAnalyticsAgent().predict(reports)
    data = analytics.model_dump(mode="json")

    columns = st.columns(5)
    columns[0].metric("Defects analyzed", data["submissions_with_pipeline_output"])
    columns[1].metric("Recurring share", f"{data['recurrence_rate']}%")
    columns[2].metric("Duplicate rate", f"{data['duplicate_rate']}%")
    columns[3].metric("Systemic patterns", len(data["systemic_patterns"]))
    columns[4].metric("Learned fixes", data["knowledge_base_entries"])

    for note in data["notes"]:
        st.caption(note)

    if not data["themes"]:
        st.info("Submit and analyze bugs to build the defect pattern view.")
        return

    st.markdown("### Recurring defect themes")
    st.caption(
        "A theme groups defects by the failure the pipeline extracted (root exception) "
        "and the component it affected, so differently worded reports of the same "
        "failure land together."
    )
    st.dataframe(
        [
            {
                "Theme": theme["theme"],
                "Occurrences": theme["occurrences"],
                "Share": theme["share_percentage"],
                "First seen": (theme["first_seen"] or "")[:19],
                "Last seen": (theme["last_seen"] or "")[:19],
                "Examples": ", ".join(theme["example_submission_ids"][:3]),
            }
            for theme in data["themes"]
        ],
        hide_index=True,
        use_container_width=True,
        column_config={
            "Share": st.column_config.ProgressColumn(
                "Share", min_value=0, max_value=100, format="%d%%"
            )
        },
    )

    st.markdown("### High-frequency affected components")
    hotspots = data["component_hotspots"]
    st.dataframe(
        [
            {
                "Component": hotspot["component"],
                "Defects": hotspot["defect_count"],
                "Share": hotspot["share_percentage"],
                "Critical/High": hotspot["high_impact_count"],
                "Top exceptions": ", ".join(hotspot["top_exceptions"]) or "None classified",
            }
            for hotspot in hotspots
        ],
        hide_index=True,
        use_container_width=True,
        column_config={
            "Share": st.column_config.ProgressColumn(
                "Share", min_value=0, max_value=100, format="%d%%"
            )
        },
    )
    if hotspots:
        st.bar_chart(
            {hotspot["component"]: hotspot["defect_count"] for hotspot in hotspots},
        )

    st.markdown("### Systemic issue patterns")
    patterns = data["systemic_patterns"]
    if not patterns:
        st.success(
            "No systemic pattern crossed its detection threshold. Defects so far look "
            "like isolated incidents rather than one underlying problem."
        )
    for pattern in patterns:
        with st.expander(f"{pattern['title']} · {pattern['affected_submissions']} submission(s)"):
            st.write(pattern["detail"])
            st.markdown("**Evidence**")
            for item in pattern["evidence"]:
                st.markdown(f"- {item}")
            st.info(pattern["recommendation"])

    left, right = st.columns(2)
    with left:
        st.markdown("**Severity distribution**")
        st.bar_chart(data["severity_distribution"])
    with right:
        st.markdown("**Exception distribution**")
        st.bar_chart(data["exception_distribution"])

    with st.expander("Complete analytics data"):
        st.json(data)


def render_knowledge_growth_panel(record: dict[str, Any]) -> None:
    """Let a reviewer confirm a fix and feed it back into retrieval."""
    submission_id = str(record.get("submission_id") or "")
    st.caption(
        f"The knowledge base holds {learned_entry_count()} confirmed fix(es). "
        "Confirming a fix makes it retrievable evidence for every future submission."
    )
    if not submission_id:
        st.info("Save the submission before confirming a fix.")
        return

    already = is_learned(submission_id)
    if already:
        st.success(
            f"{submission_id} is already in the knowledge base. Submitting again replaces "
            "its recorded fix."
        )

    remediation = (record.get("analysis") or {}).get("remediation") or {}
    default_fix = record.get("confirmed_fix") or (
        remediation.get("recommended_fix", "")
        if remediation.get("basis") == "historical"
        else ""
    )

    with st.form(f"confirm-fix-{submission_id}"):
        confirmed_fix = st.text_area(
            "Confirmed fix *",
            value=str(default_fix or ""),
            height=140,
            help="Describe the corrective action that was actually applied and verified.",
        )
        columns = st.columns(2)
        confirmed_by = columns[0].text_input(
            "Confirmed by", value=str(record.get("confirmed_by") or "")
        )
        root_cause = columns[1].text_input(
            "Confirmed root cause (optional)",
            value=str((record.get("analysis") or {}).get("root_cause", {}).get("root_cause") or "")[:200],
        )
        submitted = st.form_submit_button(
            "Add confirmed fix to knowledge base", type="primary", use_container_width=True
        )

    if not submitted:
        return

    try:
        outcome = record_confirmed_fix(record, confirmed_fix, confirmed_by, root_cause)
    except ConfirmedFixError as error:
        st.error(str(error))
        return
    except Exception as error:
        st.error(f"The confirmed fix could not be saved: {type(error).__name__}: {error}")
        return

    record["confirmed_fix"] = outcome["record"]["Resolution"]
    record["confirmed_by"] = outcome["record"]["Confirmed by"]
    record["confirmed_at"] = outcome["record"]["Confirmed at"]
    record["knowledge_base_id"] = outcome["record"]["Issue id"]
    update_report(
        submission_id,
        {
            "confirmed_fix": record["confirmed_fix"],
            "confirmed_by": record["confirmed_by"],
            "confirmed_at": record["confirmed_at"],
            "knowledge_base_id": record["knowledge_base_id"],
        },
    )

    verb = "replaced in" if outcome["replaced_previous"] else "added to"
    st.success(
        f"Confirmed fix {verb} the knowledge base as {outcome['record']['Issue id']}. "
        f"It now holds {outcome['entries']} learned fix(es)."
    )
    if outcome["indexed_immediately"]:
        st.caption("The fix was embedded into the semantic index and is searchable now.")
    else:
        st.caption(
            "The fix is searchable through the local matcher now. Run "
            "python scripts/build_index.py to add it to the semantic index."
        )
