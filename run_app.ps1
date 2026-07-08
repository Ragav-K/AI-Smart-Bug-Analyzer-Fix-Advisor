$appPath = Join-Path -Path $PSScriptRoot -ChildPath "app.py"
& "C:\Users\ragav\Python311\python.exe" -m streamlit run $appPath --server.port 8501 --server.headless true
