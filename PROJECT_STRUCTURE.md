# Project Structure

```text
.
|-- agents/                 Five single-responsibility analysis agents
|-- data/                   Local reports and generated Chroma indexes
|-- evaluation/             Agent evaluation runner and reports
|-- gitbugs/                Historical defect datasets
|-- gitbugs/samples/        Committed knowledge base (regenerable)
|-- gitbugs/learned/        Confirmed fixes written back from resolved bugs
|-- models/                 Pydantic output models
|-- pages/                  Streamlit page implementation
|-- ui/                     Reusable structured findings dashboard
|-- sample_uploads/         Ready-made files for testing the upload flow
|-- scripts/                Corpus and vector-index build tooling
|-- styles/                 Streamlit CSS
|-- tests/                  Pytest suite
|-- uploads/                Locally persisted user uploads
|-- utils/                  Parsing, retrieval, validation, and storage
|-- app.py                  Application entry function
|-- streamlit_app.py        Recommended Streamlit entry point
|-- requirements.txt        Runtime and test dependencies
`-- run_app.ps1             Windows launcher (-Python / -Port)
```

## Important modules

| Module | Responsibility |
|---|---|
| `pages/bug_submission.py` | Form rendering, submission workflow, and history |
| `ui/findings.py` | Findings tabs, confidence views, evidence, and downloads |
| `agents/orchestrator.py` | Ordered execution, shared retrieval, and result envelope |
| `agents/triage_agent.py` | Severity, priority, component, confidence, and evidence |
| `agents/log_analysis_agent.py` | Structured stack-trace and error analysis |
| `agents/root_cause_agent.py` | Grounded causal inference and evidence provenance |
| `agents/duplicate_agent.py` | Semantic re-ranking and duplicate thresholding |
| `agents/remediation_agent.py` | Historical resolution-backed repair guidance |
| `agents/pattern_analytics_agent.py` | Recurring themes, hotspots, and systemic patterns |
| `ui/analytics.py` | Analytics dashboard and the confirmed-fix panel |
| `models/analysis_models.py` | Milestone 3 Pydantic output contracts |
| `models/analytics_models.py` | Milestone 4 analytics output contracts |
| `utils/defect_analytics.py` | Pure fact extraction and portfolio aggregation |
| `utils/knowledge_base.py` | Confirmed-fix write-back into the retrieval corpus |
| `utils/scoring.py` | Duplicate re-ranking and root-cause confidence |
| `utils/rag_search.py` | Chroma retrieval, dataset normalization, and fallback routing |
| `utils/bug_similarity.py` | Bounded dependency-free local matching |
| `utils/parser.py` | Python, Java, JavaScript, and generic log parsing |
| `utils/storage.py` | Report IDs, JSON persistence, and uploaded-file storage |
| `scripts/build_index.py` | One-off vector index build for semantic retrieval |
| `scripts/build_sample_corpus.py` | Regenerates `gitbugs/samples/` from full exports |
| `scripts/demo_milestone4.py` | Five-submission demonstration with growth and analytics |
| `evaluation/evaluate_agents.py` | Repeatable evaluation and report generation |
| `evaluation/end_to_end_validation.py` | End-to-end validation across formats and dataset sizes |

## Generated or local-only paths

`data/bug_reports.json`, `data/chroma_*/`, `uploads/`, Python caches, and full raw
GitBugs CSV files are excluded by `.gitignore`.
