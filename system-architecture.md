# System Architecture

The application is a local Streamlit system with deterministic analysis and
optional semantic retrieval.

```mermaid
flowchart TD
    A["Text and uploaded files"] --> B["Validation"]
    B --> C["Text and metadata extraction"]
    C --> D["Historical-defect search"]
    C --> E["BugAnalysisOrchestrator"]
    D --> F{"Ready vector index?"}
    F -->|Yes| G["Sentence Transformer + ChromaDB"]
    F -->|No or timeout| H["Bounded local matcher"]
    E --> I["Triage agent"]
    E --> J["Log-analysis agent"]
    G --> K["Streamlit results dashboard"]
    H --> K
    I --> K
    J --> K
    K --> L["Local JSON and upload storage"]
```

## Design properties

- **Local-first:** no hosted API is required.
- **Fault-isolated:** one agent failure does not discard other results.
- **Bounded:** logs, stack frames, dataset rows, result counts, and vector-search
  time are limited.
- **Structured:** Pydantic models and stable metadata make results testable.
- **Graceful degradation:** semantic retrieval falls back to local matching.
- **Runtime separation:** reports, uploads, models, and vector indexes are not
  committed to Git.

The current implementation includes triage and log analysis. Duplicate
classification, synthesized root cause, and remediation agents remain planned.
