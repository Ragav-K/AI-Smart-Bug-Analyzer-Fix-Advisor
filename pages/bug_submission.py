from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
from PIL import Image

from utils.helpers import (
    as_bool_label,
    format_file_size,
    load_css,
    readable_timestamp,
    severity_badge_class,
)
from utils.storage import (
    ensure_project_structure,
    generate_submission_id,
    load_reports,
    save_report,
    save_uploaded_file,
)
from utils.validators import validate_submission


LANGUAGES = [
    "Python",
    "Java",
    "C",
    "C++",
    "JavaScript",
    "TypeScript",
    "Go",
    "Rust",
    "PHP",
    "Ruby",
    "Other",
]

FRAMEWORKS = [
    "None",
    "React",
    "Angular",
    "Vue",
    "Spring Boot",
    "Django",
    "Flask",
    "FastAPI",
    "Express",
    "Node.js",
    "ASP.NET",
    "Other",
]

OPERATING_SYSTEMS = ["Windows", "Linux", "macOS", "Android", "iOS", "Other"]
SEVERITIES = ["Critical", "High", "Medium", "Low"]
FILE_TYPES = ["txt", "log", "csv", "json", "xml", "pdf", "docx", "zip"]
SCREENSHOT_TYPES = ["png", "jpg", "jpeg"]


def render_bug_submission() -> None:
    """Render Module 1: Bug Submission."""
    ensure_project_structure()
    configure_page()
    render_sidebar()
    render_header()
    render_future_module_strip()

    if "submitted_reports" not in st.session_state:
        st.session_state.submitted_reports = load_reports()
    if "last_submission" not in st.session_state:
        st.session_state.last_submission = None

    render_submission_form()

    if st.session_state.last_submission:
        render_confirmation(st.session_state.last_submission)

    render_history(st.session_state.submitted_reports)
    render_footer()


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


def render_sidebar() -> None:
    with st.sidebar:
        st.markdown('<div class="sidebar-brand">Bug Analyzer</div>', unsafe_allow_html=True)
        st.markdown('<div class="sidebar-caption">Module Navigation</div>', unsafe_allow_html=True)

        nav_items = [
            ("Bug Submission", "Current Module", "active"),
            ("AI Analysis", "Coming Soon", "locked"),
            ("Duplicate Detection", "Coming Soon", "locked"),
            ("Knowledge Base", "Coming Soon", "locked"),
            ("Fix Recommendation", "Coming Soon", "locked"),
        ]

        for title, status, state in nav_items:
            marker = "*" if state == "active" else "LOCK"
            st.markdown(
                f"""
                <div class="nav-item {state}">
                    <span class="nav-icon">{marker}</span>
                    <span>
                        <strong>{title}</strong>
                        <small>{status}</small>
                    </span>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown('<div class="sidebar-spacer"></div>', unsafe_allow_html=True)
        st.markdown(
            """
            <div class="sidebar-footer">
                <strong>Version 1.0</strong>
                <span>Infosys Springboard Internship</span>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_header() -> None:
    st.markdown(
        """
        <section class="app-header">
            <div>
                <p class="eyebrow">Module 1 - Bug Submission</p>
                <h1>AI Smart Bug Analyzer & Fix Advisor</h1>
                <p>Submit software bugs, logs, screenshots, and stack traces for AI-powered defect analysis.</p>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_future_module_strip() -> None:
    labels = [
        "AI Bug Analysis",
        "RAG Knowledge Base",
        "Duplicate Bug Detection",
        "Semantic Search",
        "Root Cause Analysis",
        "Fix Recommendation",
        "Similar Bug Retrieval",
        "LLM Response",
    ]
    st.markdown('<div class="future-strip">', unsafe_allow_html=True)
    cols = st.columns(4)
    for index, label in enumerate(labels):
        with cols[index % 4]:
            st.markdown(f'<div class="future-pill">{label}</div>', unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


def render_submission_form() -> None:
    st.markdown('<div class="form-card">', unsafe_allow_html=True)
    st.markdown("### Submit a Bug Report")
    st.caption("Capture enough context for the future AI analysis pipeline.")

    st.divider()
    st.markdown("#### 1. Project Information")
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        project_name = st.text_input("Project Name", placeholder="Example: Inventory API")
    with col_b:
        language = st.selectbox("Programming Language", LANGUAGES)
    with col_c:
        framework = st.selectbox("Framework", FRAMEWORKS)
    operating_system = st.selectbox("Operating System", OPERATING_SYSTEMS)

    st.divider()
    st.markdown("#### 2. Bug Details")
    bug_title = st.text_input("Bug Title", placeholder="Example: Report generation fails")
    bug_description = st.text_area(
        "Bug Description",
        placeholder="Describe the issue in detail including the expected behavior and the actual behavior.",
        height=170,
    )

    st.divider()
    st.markdown("#### 3. Severity")
    severity = st.radio("Select Severity", SEVERITIES, horizontal=True, index=2)

    st.divider()
    st.markdown("#### 4. Steps to Reproduce")
    steps_to_reproduce = st.text_area(
        "Steps to Reproduce",
        placeholder=(
            "1. Open the application\n"
            "2. Login\n"
            "3. Click Dashboard\n"
            "4. Click Generate Report\n"
            "5. Application crashes"
        ),
        height=170,
    )

    st.divider()
    trace_col, logs_col = st.columns(2)
    with trace_col:
        st.markdown("#### 5. Stack Trace")
        stack_trace = st.text_area(
            "Stack Trace",
            placeholder="Traceback (most recent call last)...",
            height=230,
        )
    with logs_col:
        st.markdown("#### 6. Error Logs")
        error_logs = st.text_area(
            "Error Logs",
            placeholder="Paste console logs or error logs here.",
            height=230,
        )

    st.divider()
    upload_col, screenshot_col = st.columns([1.2, 1])
    with upload_col:
        st.markdown("#### 7. Upload Files")
        uploaded_files = st.file_uploader(
            "Upload logs or documents",
            type=FILE_TYPES,
            accept_multiple_files=True,
            help="Supported: .txt, .log, .csv, .json, .xml, .pdf, .docx, .zip",
        )
        render_uploaded_file_table(uploaded_files)

    with screenshot_col:
        st.markdown("#### 8. Upload Screenshot")
        screenshot = st.file_uploader(
            "Upload screenshot",
            type=SCREENSHOT_TYPES,
            accept_multiple_files=False,
            help="Supported: PNG, JPG, JPEG",
        )
        screenshot_dimensions = render_screenshot_preview(screenshot)

    st.divider()
    st.markdown("#### 9. Additional Notes")
    additional_notes = st.text_area(
        "Additional Notes",
        placeholder="Add environment notes, recent changes, related tickets, or suspected causes.",
        height=130,
    )

    draft_record = {
        "project_name": project_name,
        "language": language,
        "framework": framework,
        "operating_system": operating_system,
        "bug_title": bug_title,
        "bug_description": bug_description,
        "severity": severity,
        "steps_to_reproduce": steps_to_reproduce,
        "stack_trace": stack_trace,
        "error_logs": error_logs,
        "uploaded_files": uploaded_files,
        "screenshot": screenshot,
        "additional_notes": additional_notes,
    }

    st.markdown('<div class="submit-area">', unsafe_allow_html=True)
    submitted = st.button("Submit Bug Report", type="primary", use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

    if submitted:
        handle_submission(draft_record, screenshot_dimensions)

    st.markdown("</div>", unsafe_allow_html=True)


def render_uploaded_file_table(uploaded_files: list[Any] | None) -> None:
    if not uploaded_files:
        st.info("No files uploaded yet.")
        return

    upload_time = datetime.now().strftime("%d %b %Y, %I:%M %p")
    rows = [
        {
            "Filename": uploaded_file.name,
            "Extension": Path(uploaded_file.name).suffix.lower() or "No extension",
            "Size": format_file_size(uploaded_file.size),
            "Upload Time": upload_time,
        }
        for uploaded_file in uploaded_files
    ]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def render_screenshot_preview(screenshot: Any | None) -> dict[str, int] | None:
    if screenshot is None:
        st.info("No screenshot uploaded yet.")
        return None

    image = Image.open(screenshot)
    dimensions = {"width": image.width, "height": image.height}
    st.image(image, caption=screenshot.name, use_container_width=True)
    met_a, met_b = st.columns(2)
    met_a.metric("Width", f"{image.width}px")
    met_b.metric("Height", f"{image.height}px")
    return dimensions


def handle_submission(
    draft_record: dict[str, Any],
    screenshot_dimensions: dict[str, int] | None,
) -> None:
    validation_record = {
        **draft_record,
        "uploaded_files": draft_record["uploaded_files"] or [],
        "screenshot": draft_record["screenshot"],
    }
    errors = validate_submission(validation_record)
    if errors:
        for error in errors:
            st.error(error)
        return

    submission_id = generate_submission_id()
    timestamp = datetime.now().isoformat(timespec="seconds")

    uploaded_metadata = [
        save_uploaded_file(uploaded_file, submission_id)
        for uploaded_file in draft_record["uploaded_files"] or []
    ]

    screenshot_metadata = None
    if draft_record["screenshot"] is not None:
        screenshot_metadata = save_uploaded_file(
            draft_record["screenshot"],
            submission_id,
            is_screenshot=True,
        )
        screenshot_metadata["dimensions"] = screenshot_dimensions

    record = {
        "submission_id": submission_id,
        "project_name": draft_record["project_name"].strip(),
        "language": draft_record["language"],
        "framework": draft_record["framework"],
        "operating_system": draft_record["operating_system"],
        "bug_title": draft_record["bug_title"].strip(),
        "bug_description": draft_record["bug_description"].strip(),
        "severity": draft_record["severity"],
        "steps_to_reproduce": draft_record["steps_to_reproduce"].strip(),
        "stack_trace": draft_record["stack_trace"].strip(),
        "error_logs": draft_record["error_logs"].strip(),
        "uploaded_files": uploaded_metadata,
        "screenshot": screenshot_metadata,
        "additional_notes": draft_record["additional_notes"].strip(),
        "timestamp": timestamp,
    }

    save_report(record)
    st.session_state.submitted_reports = load_reports()
    st.session_state.last_submission = record
    st.success("Bug report submitted successfully.")


def render_confirmation(record: dict[str, Any]) -> None:
    st.markdown('<div class="confirmation-card">', unsafe_allow_html=True)
    st.markdown("### Submission Confirmation")
    col_1, col_2, col_3 = st.columns(3)
    col_1.metric("Submission ID", record["submission_id"])
    col_2.metric("Timestamp", readable_timestamp(record["timestamp"]))
    col_3.metric("Severity", record["severity"])

    col_4, col_5, col_6 = st.columns(3)
    col_4.metric("Project", record["project_name"])
    col_5.metric("Language / Framework", f"{record['language']} / {record['framework']}")
    col_6.metric("Uploaded Files", len(record["uploaded_files"]))

    st.markdown(
        f"""
        <div class="confirmation-grid">
            <span><strong>Screenshot Uploaded:</strong> {as_bool_label(record["screenshot"])}</span>
            <span><strong>Operating System:</strong> {record["operating_system"]}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)


def render_history(reports: list[dict[str, Any]]) -> None:
    st.markdown("## Session History")
    if not reports:
        st.info("Submitted bug reports will appear here.")
        return

    for report in reversed(reports):
        title = (
            f"{report['submission_id']} | {report['bug_title']} | "
            f"{report['severity']} | {readable_timestamp(report['timestamp'])}"
        )
        with st.expander(title):
            badge_class = severity_badge_class(report["severity"])
            st.markdown(
                f"""
                <div class="history-summary">
                    <span class="severity-badge {badge_class}">{report["severity"]}</span>
                    <span>{report["project_name"]}</span>
                    <span>{report["language"]} / {report["framework"]}</span>
                    <span>{report["operating_system"]}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

            info_col, detail_col = st.columns([0.9, 1.1])
            with info_col:
                st.markdown("#### Project Information")
                st.write(f"Project: {report['project_name']}")
                st.write(f"Language: {report['language']}")
                st.write(f"Framework: {report['framework']}")
                st.write(f"Operating System: {report['operating_system']}")

                st.markdown("#### Uploaded Files")
                render_saved_files(report.get("uploaded_files", []))

                st.markdown("#### Screenshot Preview")
                render_saved_screenshot(report.get("screenshot"))

            with detail_col:
                st.markdown("#### Description")
                st.write(report.get("bug_description") or "Not provided.")
                st.markdown("#### Steps to Reproduce")
                st.code(report.get("steps_to_reproduce") or "Not provided.", language="text")
                st.markdown("#### Stack Trace")
                st.code(report.get("stack_trace") or "Not provided.", language="text")
                st.markdown("#### Error Logs")
                st.code(report.get("error_logs") or "Not provided.", language="text")
                st.markdown("#### Notes")
                st.write(report.get("additional_notes") or "No additional notes.")


def render_saved_files(files: list[dict[str, Any]]) -> None:
    if not files:
        st.write("No files uploaded.")
        return

    rows = [
        {
            "Filename": item["filename"],
            "Extension": item["extension"],
            "Size": format_file_size(item["size_bytes"]),
            "Upload Time": readable_timestamp(item["upload_time"]),
        }
        for item in files
    ]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def render_saved_screenshot(screenshot: dict[str, Any] | None) -> None:
    if not screenshot:
        st.write("No screenshot uploaded.")
        return

    path = Path(screenshot["path"])
    if not path.exists():
        st.warning("Screenshot file is missing from local storage.")
        return

    st.image(str(path), caption=screenshot["filename"], use_container_width=True)
    dimensions = screenshot.get("dimensions") or {}
    if dimensions:
        st.caption(f"{dimensions.get('width')}px x {dimensions.get('height')}px")


def render_footer() -> None:
    st.markdown(
        """
        <footer class="app-footer">
            <strong>AI Smart Bug Analyzer & Fix Advisor</strong>
            <span>Developed as part of Infosys Springboard Internship</span>
        </footer>
        """,
        unsafe_allow_html=True,
    )
