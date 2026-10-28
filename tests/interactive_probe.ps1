# Wrapper so `& '...\interactive_probe.ps1'` works directly in PowerShell —
# running the .py file the same way just opens it via file association
# instead of executing it, since PowerShell doesn't run .py through Python.
$python = "C:\Users\lcdan\AppData\Local\Programs\Python\Python312\python.exe"
$script = Join-Path $PSScriptRoot "interactive_probe.py"
& $python $script @args
