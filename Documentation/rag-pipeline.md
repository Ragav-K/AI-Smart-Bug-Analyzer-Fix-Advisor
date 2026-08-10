# Historical-Defect Retrieval Pipeline

The current project implements retrieval, not an LLM generation layer.
Historical CSV, JSON, JSONL, XLS, and XLSX files below `gitbugs/` are normalized
into a common defect record.

## Semantic path

1. Useful fields are combined into searchable text.
2. `all-MiniLM-L6-v2` creates normalized embeddings.
3. ChromaDB persists the vectors under `data/chroma_gitbugs/`.
4. A submitted report is embedded and queried against the ready collection.
5. The closest matches receive bounded similarity scores and plain-language
   match reasons.

The interactive search path never builds the index. This keeps a submission
from unexpectedly waiting several minutes.

## Local fallback

If the index is absent, empty, unavailable, or exceeds the 15-second search
timeout, the system falls back to a dependency-free token matcher. The fallback
limits rows and text sizes so response time and memory use remain bounded.

## Current boundary

Retrieved defects are displayed alongside deterministic agent analysis. A future
root-cause or remediation agent may consume this evidence, but the current code
does not call LangChain or a hosted LLM.

See [DATASETS.md](DATASETS.md) for data formats and repository policy.
