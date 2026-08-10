# Troubleshooting

## `streamlit` is not recognized

Activate the virtual environment and launch Streamlit through Python:

```powershell
.\.venv\Scripts\Activate.ps1
python -m streamlit run streamlit_app.py
```

## PowerShell blocks virtual-environment activation

Use a process-scoped policy:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

## Semantic search shows `Local fallback`

This is expected when either the Chroma index is not ready or
`all-MiniLM-L6-v2` is not available in the local model cache. The application
continues with bounded token similarity. See [INSTALLATION.md](INSTALLATION.md)
for optional index setup.

## Chroma index is stale or damaged

Stop Streamlit, remove `data/chroma_gitbugs/`, and rebuild the index from the
source datasets. The directory is generated and excluded from Git.

## No similar bugs are returned

Confirm that `gitbugs/` contains supported dataset files. A normal clone includes
compact `*-combined.csv` samples. Also provide a descriptive title, error
message, and stack trace so the matcher has useful terms.

## Uploaded text is missing

Verify the extension is supported and the document is readable. Images are
stored as evidence but the current project does not perform OCR.

## Tests appear slow on first run

Imports from ChromaDB, Pandas, and Sentence Transformers can add startup time.
Subsequent runs are normally faster because Python and operating-system caches
are warm.

## The provided `run_app.ps1` fails

That helper contains a machine-specific Python path. Use the portable command:

```powershell
python -m streamlit run streamlit_app.py
```
