from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st

from ui.analytics import render_analytics_dashboard, render_knowledge_growth_panel
from ui.findings import render_findings_dashboard
from utils.helpers import format_file_size, load_css
from utils.logging_config import get_agent_logger
from utils.rag_search import (
    INDEX_READY_MARKER,
    MODEL_NAME,
    VECTOR_DIR,
    extract_uploaded_text,
    is_vector_index_ready,
    search_similar_bugs,
    warm_retrieval_backend,
)
from utils.storage import (
    ensure_project_structure,
    generate_submission_id,
    load_reports,
    save_report,
    save_uploaded_file,
)
from utils.validators import validate_submission

LOGGER = get_agent_logger(__name__)

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
    # Start loading the embedding model now, in the background, so it is ready
    # by the time the first report is submitted rather than costing that
    # submission a timeout and a silent fallback.
    warm_retrieval_backend()
    render_header()
    render_knowledge_base_status()

    if "analysis_history" not in st.session_state:
        saved_reports = [
            report
            for report in reversed(load_reports())
            if report.get("analysis")
        ][:25]
        st.session_state.analysis_history = saved_reports
    if "last_submission" not in st.session_state:
        history = st.session_state.analysis_history
        st.session_state.last_submission = history[0] if history else None

    render_sidebar()
    render_submission_form()

    if st.session_state.last_submission:
        render_results(st.session_state.last_submission)

def configure_page() -> None:
    st.set_page_config(
        page_title="AI Smart Bug Analyzer & Fix Advisor",
        page_icon="BUG",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    css = load_css()
    if css:
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def render_knowledge_base_status() -> None:
    # Opening ChromaDB here made every fresh page load wait for the full
    # database dependency stack. The marker is written only after a successful
    # index build, so a filesystem check is sufficient for startup status.
    if is_vector_index_ready():
        st.caption("Historical Defect Knowledge Base ready (semantic retrieval).")
        return

    if VECTOR_DIR.exists() and any(
        path != INDEX_READY_MARKER for path in VECTOR_DIR.iterdir()
    ):
        message = "Historical Defect Knowledge Base build is incomplete."
    else:
        message = "Historical Defect Knowledge Base has not been indexed yet."
    st.info(
        f"{message} Searches use the local token fallback until the index is "
        "built. Build it once with:  python scripts/build_index.py"
    )


def render_header() -> None:
    st.markdown(
        """
        <section class="app-header">
            <p class="eyebrow">Milestone 4 - Defect Pattern Analytics &amp; a Growing Knowledge Base</p>
            <h1>AI Smart Bug Analyzer &amp; Fix Advisor</h1>
            <p>Trace the failure, identify its cause, detect duplicates, recommend an evidence-backed fix, and learn from every confirmed resolution.</p>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar() -> None:
    """Render recent submission history and pipeline status."""
    with st.sidebar:
        st.header("Analysis workspace")
        latest = st.session_state.get("last_submission") or {}
        analysis = latest.get("analysis") or {}
        executed = (analysis.get("metadata") or {}).get("agents_executed") or []
        if latest:
            st.caption(f"Current: {latest.get('submission_id', 'Unknown')}")
            st.progress(min(1.0, len(executed) / 5))
            st.write(f"{len(executed)}/5 agents completed")
        else:
            st.caption("Submit a bug to start the five-agent pipeline.")
        st.divider()
        st.subheader("Submission history")
        history = st.session_state.get("analysis_history") or []
        if not history:
            st.caption("No analyzed submissions have been saved yet.")
        for item in history[:10]:
            if st.button(
                f"{item.get('submission_id', 'Unknown')} · {shorten(item.get('bug_title', 'Untitled'), 28)}",
                key=f"history-{item.get('submission_id')}",
                use_container_width=True,
            ):
                st.session_state.last_submission = item
                st.rerun()


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

    submission_id: str | None = None
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
                similar_bugs = search_similar_bugs(submitted_text, limit=10)
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

        with st.status("Running the five-agent analysis pipeline...", expanded=True) as status:
            # Agent schemas and Pydantic models are needed only after the user
            # submits a report, not while the web form is starting.
            from agents.orchestrator import BugAnalysisOrchestrator

            st.write("Interpreting logs and triaging impact")
            record["analysis"] = BugAnalysisOrchestrator().analyze(record, submission_id)
            st.write("Grounding root cause, duplicates, and remediation")
            status.update(label="Analysis complete", state="complete", expanded=False)

        save_report(record)
    except Exception as error:
        # The operator needs the real cause; the previous generic message made a
        # model failure, a disk error, and a validation error indistinguishable.
        LOGGER.exception("Bug submission failed", extra={"submission_id": submission_id or "UNSAVED"})
        st.error(f"Unable to submit the bug report: {type(error).__name__}: {error}")
        st.caption("The full traceback was written to the application log.")
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
    render_findings_dashboard(record.get("analysis") or {}, record)
    st.markdown("## Historical Knowledge Search")
    render_search_statistics(record.get("search_stats", {}))
    st.markdown("## Top Similar Historical Bugs")
    render_similar_bugs(record.get("similar_bugs") or [])

    st.markdown("## Confirm the Fix (Knowledge Base Growth)")
    render_knowledge_growth_panel(record)

    st.markdown("## Defect Pattern Analytics")
    st.caption(
        "Recurring themes, high-frequency components, and systemic issues measured "
        "across every analyzed submission."
    )
    render_analytics_dashboard(load_reports())


def render_similar_bugs(similar_bugs: list[dict[str, Any]]) -> None:
    if not similar_bugs:
        st.info(
            "No similar historical defects were found.\n\n"
            "Your submitted bug appears to be unique.\n\n"
            "Confirm its fix below to add it to the historical defect knowledge base."
        )
        return

    for index, bug in enumerate(similar_bugs[:5], start=1):
        render_similarity_card(index, bug)


def render_similarity_card(index: int, bug: dict[str, Any]) -> None:
    title = bug.get("title") or "Untitled historical bug"
    description = bug.get("description") or bug.get("full_text") or "No description available."
    meta = "".join(
        render_optional_meta(label, bug.get(key))
        for label, key in (
            ("Project", "project_name"),
            ("Priority", "priority"),
            ("Status", "status"),
            ("Labels", "labels"),
            ("Root Cause", "root_cause"),
            ("Resolution", "resolution"),
        )
    )
    # Emitted as one line: Streamlit runs this through a Markdown parser
    # first, and an indented HTML block would be treated as a code fence,
    # which leaks the raw closing tags into the page.
    st.markdown(
        '<article class="result-card">'
        '<div class="result-card-header">'
        f'<span class="match-badge {bug.get("badge_class", "match-low")}">'
        f'{escape_html(bug.get("badge_label", "Match"))}</span>'
        f'<strong>Similarity: {bug.get("similarity_percentage", 0)}%</strong>'
        "</div>"
        f"<h3>{index}. {escape_html(title)}</h3>"
        f'<div class="bug-id">{escape_html(bug.get("bug_id", "Unknown Bug ID"))}</div>'
        f"<p>{escape_html(shorten(description, 360))}</p>"
        f'<div class="result-meta">{meta}</div>'
        f"{render_match_reasons(bug.get('match_reasons', []))}"
        "</article>",
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
        '<section class="stats-grid">'
        f'<div><span>Historical Bugs</span><strong>{int(merged["historical_bugs_indexed"]):,}</strong></div>'
        f'<div><span>Embedding Model</span><strong>{escape_html(merged["embedding_model"])}</strong></div>'
        f'<div><span>Vector Database</span><strong>{escape_html(merged["vector_database_status"])}</strong></div>'
        f'<div><span>Search Time</span><strong>{merged["search_time_seconds"]:.2f} seconds</strong></div>'
        "</section>",
        unsafe_allow_html=True,
    )


def render_match_reasons(reasons: list[str]) -> str:
    if not reasons:
        return ""
    items = "".join(f"<li>{escape_html(reason)}</li>" for reason in reasons[:4])
    return (
        '<div class="match-reasons">'
        "<strong>Why this matched</strong>"
        f"<ul>{items}</ul>"
        "</div>"
    )


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
