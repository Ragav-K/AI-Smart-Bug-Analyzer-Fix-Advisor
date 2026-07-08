# RAG Pipeline

The historical knowledge base is built from real bug datasets, such as Mozilla, Apache, and Eclipse bug reports from Kaggle. These reports give the system examples of past failures, fixes, duplicate bugs, and root causes.

The pipeline first cleans the dataset and keeps the useful fields, such as title, description, comments, status, component, and resolution. Then each bug report is converted into embeddings using `all-MiniLM-L6-v2`.

Those embeddings are stored in ChromaDB. When a new bug is submitted, the system turns the new report into an embedding too, then searches ChromaDB for similar historical bugs.

The LLM does not answer from memory alone. It gets the closest matching bug reports as context, then uses them to explain the likely root cause, duplicate match, and suggested fix.

In simple terms:

- Kaggle bug data becomes the project memory.
- Sentence Transformers convert bug text into searchable meaning.
- ChromaDB finds similar old bugs.
- LangChain passes those matches to the LLM.
- The final answer is grounded in past bug data.
