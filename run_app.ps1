# Launch the Streamlit app using the interpreter on PATH.
# Override for a specific interpreter:  .\run_app.ps1 -Python "C:\Python311\python.exe"
param(
    [string]$Python = $(if ($env:BUG_ANALYZER_PYTHON) { $env:BUG_ANALYZER_PYTHON } else { "python" }),
    [int]$Port = 8501
)

$appPath = Join-Path -Path $PSScriptRoot -ChildPath "app.py"
Push-Location -LiteralPath $PSScriptRoot
try {
    & $Python -m streamlit run $appPath `
        --server.port $Port `
        --server.headless true `
        --server.fileWatcherType none `
        --browser.gatherUsageStats false
}
finally {
    Pop-Location
}
