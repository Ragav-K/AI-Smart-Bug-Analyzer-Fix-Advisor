from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st

from agents.orchestrator import BugAnalysisOrchestrator
from utils.helpers import format_file_size, load_css
from utils.rag_search import (
    MODEL_NAME,
    extract_uploaded_text,
    get_vector_collection,
    is_vector_index_ready,
    search_similar_bugs,
)
from utils.storage import (
    ensure_project_structure,
    generate_submission_id,
    save_report,
    save_uploaded_file,
)
from utils.validators import validate_submission


FILE_TYPES = [
    "txt",
    "log",
    "pdf",
    "docx",
    "png",
    "jpg",
    "jpeg",
    "zip",
    "java",
    "py",
    "js",
    "ts",
    "cpp",
    "json",
    "xml",
]


def render_bug_submission() -> None:
    """Render bug submission, RAG search, and automatic multi-agent analysis."""
    ensure_project_structure()
    configure_page()
    render_header()
    render_knowledge_base_status()

    if "last_submission" not in st.session_state:
        st.session_state.last_submission = None
    if "analysis_history" not in st.session_state:
        st.session_state.analysis_history = []

    render_submission_form()

    if st.session_state.last_submission:
        render_results(st.session_state.last_submission)

def configure_page() -> None:
    st.set_page_config(
        page_title="AI Smart Bug Analyzer & Fix Advisor",
        page_icon="BUG",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    css = load_css()
    if css:
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def render_knowledge_base_status() -> None:
    try:
        collection = get_vector_collection(build_if_missing=False)
        indexed_count = collection.count()
    except Exception:
        st.warning("Historical Defect Knowledge Base is not available yet.")
        return

    if indexed_count and is_vector_index_ready():
        st.caption(f"Historical Defect Knowledge Base ready: {indexed_count:,} defects indexed.")
    elif indexed_count:
        st.info(
            f"Historical Defect Knowledge Base build is incomplete "
            f"({indexed_count:,} defects indexed). Searches will use the fast local fallback."
        )
    else:
        st.info(
            "Historical Defect Knowledge Base is ready to initialize. "
            "Until the offline index is built, searches will use the fast local fallback."
        )


def render_header() -> None:
    st.markdown(
        """
        <section class="app-header">
            <p class="eyebrow">Milestone 2 - Multi-Agent Bug Intelligence</p>
            <h1>AI Smart Bug Analyzer & Fix Advisor</h1>
            <p>Submit once to triage impact, interpret logs, and search similar historical defects.</p>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_submission_form() -> None:
    with st.container():
        st.markdown('<div class="form-card">', unsafe_allow_html=True)
        st.markdown("### Bug Submission")
        st.caption("Enter the required details, attach supporting files, and search the GitBugs knowledge base.")

        # Keep this control outside the form so changing it triggers Streamlit's
        # normal rerun and immediately updates the conditional form fields.
        submission_method = st.segmented_control(
            "Submission Method",
            options=["Text", "File", "Text + File"],
            default="Text + File",
            selection_mode="single",
            key="submission_method",
        )

        with st.form("bug_submission_form", clear_on_submit=False):
            bug_title = ""
            bug_description = ""
            steps_to_reproduce = ""
            expected_result = ""
            actual_result = ""
            environment = ""
            uploaded_files: list[Any] = []

            if submission_method in {"Text", "Text + File"}:
                bug_title = st.text_input(
                    "Bug Title *",
                    placeholder="Application crashes when clicking Login",
                )
                bug_description = st.text_area(
                    "Bug Description *",
                    placeholder="Describe what went wrong, including any visible error messages or stack trace.",
                    height=180,
                )
                col_left, col_right = st.columns(2)
                with col_left:
                    steps_to_reproduce = st.text_area(
                        "Steps to Reproduce",
                        placeholder="1. Open the app\n2. Go to Login\n3. Click Submit",
                        height=150,
                    )
                    actual_result = st.text_area(
                        "Actual Result",
                        placeholder="The app crashes and shows a NullPointerException.",
                        height=130,
                    )
                with col_right:
                    expected_result = st.text_area(
                        "Expected Result",
                        placeholder="The user should be signed in and redirected to the dashboard.",
                        height=150,
                    )
                    environment = st.text_area(
                        "Environment",
                        placeholder="OS: Windows 11\nBrowser: Chrome 126\nApp Version: 1.4.2",
                        height=130,
                    )

            if submission_method in {"File", "Text + File"}:
                st.markdown("#### Upload Supporting Files")
                uploaded_files = st.file_uploader(
                    "Drag and drop files here",
                    type=FILE_TYPES,
                    accept_multiple_files=True,
                    label_visibility="collapsed",
                    help="Supported: txt, log, pdf, docx, png, jpg, jpeg, zip, java, py, js, ts, cpp, json, xml",
                )
                render_uploaded_files(uploaded_files)

            submitted = st.form_submit_button(
                "Analyze Bug",
                type="primary",
                use_container_width=True,
            )

        st.markdown("</div>", unsafe_allow_html=True)

    if submitted:
        handle_submission(
            {
                "submission_method": submission_method,
                "bug_title": bug_title,
                "bug_description": bug_description,
                "steps_to_reproduce": steps_to_reproduce,
                "expected_result": expected_result,
                "actual_result": actual_result,
                "environment": environment,
                "uploaded_files": uploaded_files or [],
            }
        )


def render_uploaded_files(uploaded_files: list[Any] | None) -> None:
    if not uploaded_files:
        st.info("No supporting files uploaded yet.")
        return

    st.markdown('<div class="upload-grid">', unsafe_allow_html=True)
    for uploaded_file in uploaded_files:
        file_type = Path(uploaded_file.name).suffix.lower() or "No extension"
        st.markdown(
            f"""
            <div class="upload-card">
                <div class="file-icon">FILE</div>
                <div>
                    <strong>{escape_html(uploaded_file.name)}</strong>
                    <span>{escape_html(file_type)} &bull; {format_file_size(uploaded_file.size)}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)
    st.caption("Use the X in the upload area to remove a file before submission.")


def handle_submission(draft_record: dict[str, Any]) -> None:
    errors = validate_submission(draft_record)
    if errors:
        for error in errors:
            st.error(error)
        return

    try:
        with st.spinner("Reading uploaded files..."):
            uploaded_text_parts = [
                extract_uploaded_text(uploaded_file)
                for uploaded_file in draft_record["uploaded_files"]
            ]

        with st.spinner("Preparing search query..."):
            submitted_text = build_search_query(draft_record, uploaded_text_parts)

        submission_id = generate_submission_id()
        search_started = time.perf_counter()
        try:
            with st.spinner("Searching historical defects..."):
                similar_bugs = search_similar_bugs(submitted_text, limit=5)
                first_match = similar_bugs[0] if similar_bugs else {}
                search_backend = first_match.get("search_backend", MODEL_NAME)
                indexed_count = int(first_match.get("historical_bugs_indexed", 0))
                search_stats = {
                    "historical_bugs_indexed": indexed_count,
                    "embedding_model": search_backend,
                    "vector_database_status": (
                        "Ready" if search_backend == MODEL_NAME else "Local fallback"
                    ),
                    "search_time_seconds": round(time.perf_counter() - search_started, 2),
                }
        except Exception:
            similar_bugs = []
            search_stats = {
                "historical_bugs_indexed": 0,
                "embedding_model": MODEL_NAME,
                "vector_database_status": "Temporarily unavailable",
                "search_time_seconds": round(time.perf_counter() - search_started, 2),
            }
            st.warning("Agent analysis will continue, but historical similarity search is temporarily unavailable.")

        uploaded_metadata = [
            save_uploaded_file(uploaded_file, submission_id)
            for uploaded_file in draft_record["uploaded_files"]
        ]
        record = {
            "submission_id": submission_id,
            "submission_method": form_value(draft_record, "submission_method"),
            "bug_title": form_value(draft_record, "bug_title"),
            "bug_description": form_value(draft_record, "bug_description"),
            "steps_to_reproduce": form_value(draft_record, "steps_to_reproduce"),
            "expected_result": form_value(draft_record, "expected_result"),
            "actual_result": form_value(draft_record, "actual_result"),
            "environment": form_value(draft_record, "environment"),
            "submitted_text": submitted_text,
            "log_text": "\n\n".join(part for part in uploaded_text_parts if part.strip()),
            "uploaded_files": uploaded_metadata,
            "similar_bugs": similar_bugs,
            "search_stats": search_stats,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }

        with st.spinner("Running Triage and Log Analysis agents..."):
            record["analysis"] = BugAnalysisOrchestrator().analyze(record, submission_id)

        save_report(record)
    except Exception:
        st.error("Unable to submit the bug report. Please verify the uploaded files and try again.")
        return

    st.session_state.last_submission = record
    st.session_state.analysis_history = [
        record,
        *[
            item for item in st.session_state.analysis_history
            if item.get("submission_id") != submission_id
        ],
    ][:25]
    st.success("Bug submitted and analyzed successfully")


def form_value(record: dict[str, Any], key: str) -> str:
    return str(record.get(key) or "").strip()


def build_search_query(record: dict[str, Any], uploaded_text_parts: list[str]) -> str:
    sections = [
        ("Bug Title", record.get("bug_title")),
        ("Bug Description", record.get("bug_description")),
        ("Steps to Reproduce", record.get("steps_to_reproduce")),
        ("Expected Result", record.get("expected_result")),
        ("Actual Result", record.get("actual_result")),
        ("Environment", record.get("environment")),
        ("Extracted Uploaded File Text", "\n\n".join(uploaded_text_parts)),
    ]
    return "\n\n".join(
        f"{label}:\n{str(value).strip()}"
        for label, value in sections
        if value and str(value).strip()
    )


def render_results(record: dict[str, Any]) -> None:
    st.markdown("## AI Analysis Dashboard")
    render_analysis_dashboard(record.get("analysis") or {})
    st.markdown("## Historical Knowledge Search")
    render_search_statistics(record.get("search_stats", {}))
    st.markdown("## Top Similar Historical Bugs")
    similar_bugs = record.get("similar_bugs") or []
    if not similar_bugs:
        st.info(
            "No similar historical defects were found.\n\n"
            "Your submitted bug appears to be unique.\n\n"
            "It can be added to improve the historical defect knowledge base in future."
        )
        return

    for index, bug in enumerate(similar_bugs, start=1):
        render_similarity_card(index, bug)


def render_analysis_dashboard(analysis: dict[str, Any]) -> None:
    """Render the stable orchestrator response as an issue-tracker dashboard."""
    triage = analysis.get("triage") or {}
    log_analysis = analysis.get("log_analysis") or {}
    metadata = analysis.get("metadata") or {}
    if not triage and not log_analysis:
        st.warning("Agent analysis is unavailable for this submission.")
        return

    if triage:
        st.markdown(
            f"""
            <section class="agent-summary-grid">
                <div class="summary-card"><span>Severity</span><strong class="badge severity-{escape_html(str(triage.get('severity', 'medium')).lower())}">{escape_html(triage.get('severity', 'Unknown'))}</strong></div>
                <div class="summary-card"><span>Priority</span><strong class="badge priority-badge">{escape_html(triage.get('priority', 'Unknown'))}</strong></div>
                <div class="summary-card"><span>Component</span><strong class="badge component-badge">{escape_html(triage.get('component', 'Other'))}</strong></div>
                <div class="summary-card"><span>Processing Time</span><strong>{float(metadata.get('processing_time_seconds', 0)):.3f}s</strong></div>
            </section>
            """,
            unsafe_allow_html=True,
        )
        left, right = st.columns([2, 1])
        with left:
            st.markdown("### Triage Agent")
            st.markdown(f"**Business impact:** {triage.get('business_impact', 'Not determined')}")
            st.info(triage.get("reasoning", "No explanation available."))
        with right:
            confidence = int(triage.get("confidence", 0))
            st.metric("Triage Confidence", f"{confidence}%")
            st.progress(confidence / 100)
        evidence = triage.get("evidence") or []
        if evidence:
            st.markdown("#### Supporting Evidence")
            st.dataframe(
                [{"Signal": signal, "Source": "Report / stack trace"} for signal in evidence],
                hide_index=True,
                use_container_width=True,
            )

    if log_analysis:
        st.markdown("### Log Analysis Agent")
        first, second, third = st.columns(3)
        first.metric("Exception", log_analysis.get("exception_type") or "Not detected")
        second.metric("Language", log_analysis.get("language") or "Unknown")
        third.metric("Confidence", f"{int(log_analysis.get('confidence', 0))}%")
        st.markdown(
            f"""
            <section class="detail-grid">
                <div><span>Error Message</span><strong>{escape_html(log_analysis.get('error_message') or 'Not available')}</strong></div>
                <div><span>Failure Point</span><strong>{escape_html(log_analysis.get('failure_point') or 'Not available')}</strong></div>
                <div><span>File / Line</span><strong>{escape_html(log_analysis.get('file') or 'Unknown')} : {escape_html(log_analysis.get('line') or '-')}</strong></div>
                <div><span>Function / Method</span><strong>{escape_html(log_analysis.get('function') or 'Unknown')}</strong></div>
                <div><span>Code Module</span><strong>{escape_html(log_analysis.get('module') or 'Unknown')}</strong></div>
                <div><span>Probable Product Area</span><strong>{escape_html(log_analysis.get('probable_module') or 'Other')}</strong></div>
            </section>
            """,
            unsafe_allow_html=True,
        )
        st.warning(f"**Root cause hint:** {log_analysis.get('probable_cause', 'Not enough evidence.')}")
        with st.expander("Call Stack Summary", expanded=True):
            for step in log_analysis.get("call_stack_summary") or []:
                st.markdown(f"- {step}")
        for warning in log_analysis.get("warnings") or []:
            st.caption(f"Parser note: {warning}")

    errors = metadata.get("agent_errors") or {}
    if errors:
        st.warning("Some agents could not complete: " + ", ".join(errors))
    with st.expander("Raw Analysis JSON"):
        st.json(analysis)


def render_similarity_card(index: int, bug: dict[str, Any]) -> None:
    title = bug.get("title") or "Untitled historical bug"
    description = bug.get("description") or bug.get("full_text") or "No description available."
    st.markdown(
        f"""
        <article class="result-card">
            <div class="result-card-header">
                <span class="match-badge {bug.get("badge_class", "match-low")}">{bug.get("badge_label", "Match")}</span>
                <strong>Similarity: {bug.get("similarity_percentage", 0)}%</strong>
            </div>
            <h3>{index}. {escape_html(title)}</h3>
            <div class="bug-id">{escape_html(bug.get("bug_id", "Unknown Bug ID"))}</div>
            <p>{escape_html(shorten(description, 360))}</p>
            <div class="result-meta">
                {render_optional_meta("Project", bug.get("project_name"))}
                {render_optional_meta("Priority", bug.get("priority"))}
                {render_optional_meta("Status", bug.get("status"))}
                {render_optional_meta("Labels", bug.get("labels"))}
                {render_optional_meta("Root Cause", bug.get("root_cause"))}
                {render_optional_meta("Resolution", bug.get("resolution"))}
            </div>
            {render_match_reasons(bug.get("match_reasons", []))}
        </article>
        """,
        unsafe_allow_html=True,
    )

    with st.expander("Expand Details"):
        details = {
            "Bug ID": bug.get("bug_id"),
            "Title": title,
            "Project Name": bug.get("project_name"),
            "Priority": bug.get("priority"),
            "Status": bug.get("status"),
            "Labels": bug.get("labels"),
            "Root Cause": bug.get("root_cause"),
            "Resolution": bug.get("resolution"),
            "Source File": bug.get("source_file"),
        }
        for label, value in details.items():
            if value:
                st.markdown(f"**{label}:** {value}")
        st.markdown("**Full Historical Bug:**")
        st.write(bug.get("full_text") or description)


def render_search_statistics(stats: dict[str, Any]) -> None:
    default_stats = {
        "historical_bugs_indexed": 0,
        "embedding_model": MODEL_NAME,
        "vector_database_status": "Ready",
        "search_time_seconds": 0,
    }
    merged = {**default_stats, **(stats or {})}
    st.markdown(
        f"""
        <section class="stats-grid">
            <div><span>Historical Bugs</span><strong>{int(merged["historical_bugs_indexed"]):,}</strong></div>
            <div><span>Embedding Model</span><strong>{escape_html(merged["embedding_model"])}</strong></div>
            <div><span>Vector Database</span><strong>{escape_html(merged["vector_database_status"])}</strong></div>
            <div><span>Search Time</span><strong>{merged["search_time_seconds"]:.2f} seconds</strong></div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_match_reasons(reasons: list[str]) -> str:
    if not reasons:
        return ""
    items = "".join(f"<li>{escape_html(reason)}</li>" for reason in reasons[:4])
    return f"""
        <div class="match-reasons">
            <strong>Why this matched</strong>
            <ul>{items}</ul>
        </div>
    """


def render_optional_meta(label: str, value: Any) -> str:
    if not value:
        return ""
    return f"<span><b>{escape_html(label)}:</b> {escape_html(shorten(str(value), 140))}</span>"


def shorten(text: str, limit: int) -> str:
    cleaned = " ".join(str(text or "").split())
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[: limit - 3].rstrip()}..."


def escape_html(value: Any) -> str:
    text = str(value or "")
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )
