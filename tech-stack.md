# Tech Stack

| Area | Tool | Why it was picked |
|---|---|---|
| Language | Python 3.11 | Application, agents, retrieval, persistence, and tests |
| UI | Streamlit | Interactive form, uploads, status, and results dashboard |
| Validation | Pydantic 1.10–2.x | Stable structured agent outputs |
| Data processing | Pandas and OpenPyXL | CSV and spreadsheet ingestion |
| Embeddings | Sentence Transformers `all-MiniLM-L6-v2` | Local semantic representation |
| Vector database | ChromaDB | Persistent local cosine-similarity search |
| Local fallback | Python counters and cosine similarity | Retrieval without model or index |
| Document parsing | PyPDF2 and python-docx | Text extraction from uploaded documents |
| Images | Pillow | Uploaded image handling |
| Persistence | JSON and local filesystem | Lightweight report and file storage |
| Testing | Pytest | Unit and integration coverage |
| Version control | Git and GitHub | Collaboration and project history |

## Not currently used

The codebase does not currently require FastAPI, Flask, LangChain, MongoDB,
Cloudinary, or a hosted LLM. These should not be described as runtime
dependencies unless they are implemented in a future change.
