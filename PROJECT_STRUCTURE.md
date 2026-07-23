# Project Structure

```text
.
|-- agents/                 Triage, log analysis, and orchestration
|-- data/                   Local reports and generated Chroma indexes
|-- evaluation/             Agent evaluation runner and reports
|-- gitbugs/                Historical defect datasets and compact samples
|-- models/                 Pydantic output models
|-- pages/                  Streamlit page implementation
|-- schemas/                JSON schema helpers
|-- styles/                 Streamlit CSS
|-- tests/                  Pytest suite
|-- uploads/                Locally persisted user uploads
|-- utils/                  Parsing, retrieval, validation, and storage
|-- app.py                  Application entry function
|-- streamlit_app.py        Recommended Streamlit entry point
|-- requirements.txt        Runtime and test dependencies
`-- run_app.ps1             Machine-specific Windows launcher
```

## Important modules

| Module | Responsibility |
|---|---|
| `pages/bug_submission.py` | Form rendering, submission workflow, and results UI |
| `agents/orchestrator.py` | Independent agent execution and stable result envelope |
| `agents/triage_agent.py` | Severity, priority, component, confidence, and evidence |
| `agents/log_analysis_agent.py` | Structured stack-trace and error analysis |
| `utils/rag_search.py` | Chroma retrieval, dataset normalization, and fallback routing |
| `utils/bug_similarity.py` | Bounded dependency-free local matching |
| `utils/parser.py` | Python, Java, JavaScript, and generic log parsing |
| `utils/storage.py` | Report IDs, JSON persistence, and uploaded-file storage |
| `evaluation/evaluate_agents.py` | Repeatable evaluation and report generation |

## Generated or local-only paths

`data/bug_reports.json`, `data/chroma_*/`, `uploads/`, Python caches, and full raw
GitBugs CSV files are excluded by `.gitignore`.
