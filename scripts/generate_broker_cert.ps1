# Wrapper so `& '...\generate_broker_cert.ps1'` works directly in PowerShell —
# running the .py file the same way just opens it via file association
# instead of executing it, since PowerShell doesn't run .py through Python.
$python = "C:\Users\lcdan\AppData\Local\Programs\Python\Python312\python.exe"
$script = Join-Path $PSScriptRoot "generate_broker_cert.py"
& $python $script @args
