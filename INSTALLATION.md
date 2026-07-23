# Installation

## Requirements

- Python 3.11 recommended
- Git
- Approximately 2 GB of free space for Python, ML dependencies, and optional
  model/index files

No OpenAI or other hosted-model API key is required.

## Windows setup

```powershell
git clone https://github.com/Ragav-K/AI-Smart-Bug-Analyzer-Fix-Advisor.git
cd AI-Smart-Bug-Analyzer-Fix-Advisor
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m streamlit run streamlit_app.py
```

## macOS or Linux setup

```bash
git clone https://github.com/Ragav-K/AI-Smart-Bug-Analyzer-Fix-Advisor.git
cd AI-Smart-Bug-Analyzer-Fix-Advisor
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m streamlit run streamlit_app.py
```

## Entry points

- `streamlit_app.py` is the recommended conventional Streamlit entry point.
- `app.py` contains the application `main()` function.
- `run_app.ps1` is a machine-specific convenience script and may need its
  Python path changed before use.

## Optional semantic-search setup

The application requests `all-MiniLM-L6-v2` with `local_files_only=True`. This
prevents an interactive request from waiting on a model download. If the model
is not already present in the local Hugging Face cache, the app uses local token
similarity instead.

To build a persistent Chroma index, make the model available locally and call
the index builder from the repository root:

```powershell
python -c "from utils.rag_search import get_vector_collection; c = get_vector_collection(); print(c.count())"
```

Generated index files are stored under `data/chroma_gitbugs/` and are ignored by
Git.

## Verify the installation

```powershell
python -m pytest -q
python -m streamlit run streamlit_app.py
```

For common failures, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).
