# Tech Stack

| Area | Tool | Why it was picked |
|---|---|---|
| Frontend | Streamlit | Fast to build and easy to demo for Milestone 1. |
| Backend/API | Python with FastAPI or Flask, optional | Useful later if the AI modules need clean API endpoints. |
| AI Orchestration | LangChain | Helps connect agents, prompts, retrieval, and LLM calls. |
| LLM | OpenAI-compatible LLM | Keeps the app flexible across providers that support the same API style. |
| Embedding Model | Sentence Transformers `all-MiniLM-L6-v2` | Lightweight, popular, and good enough for semantic bug search. |
| Vector Database | ChromaDB | Simple local vector storage for matching new bugs with old ones. |
| Database | MongoDB or SQLite | MongoDB fits richer bug records; SQLite is easier for a lightweight setup. |
| File Storage | Local Storage or Cloudinary | Local storage works for demos; Cloudinary can help if the app is deployed. |
| Dataset Source | Kaggle Mozilla, Apache, Eclipse bug datasets | Gives the system real historical bug data instead of made-up examples. |
| Version Control | Git and GitHub | Tracks project changes and makes submission/review easier. |
| Deployment | Streamlit Community Cloud or Render | Both are beginner-friendly choices for sharing the app online. |
| Testing | Pytest | Simple Python testing for validators, storage, and future AI logic. |
