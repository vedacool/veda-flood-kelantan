# VEDA one-click installer for Windows (B-106). Safe to run twice.
#   .\install.ps1              install, check, start the server on http://127.0.0.1:8000
#   .\install.ps1 -NoStart     install + check only (or --no-start)
# No admin rights, no deletes, packages only from PyPI, never writes a key, never touches Docker or Nightshift.
# If Windows blocks the script: powershell -ExecutionPolicy Bypass -File .\install.ps1
param([switch]$NoStart, [int]$Port = 8000, [Parameter(ValueFromRemainingArguments = $true)][string[]]$Rest)
if ($Rest -contains "--no-start") { $NoStart = $true }      # the same flag as install.sh
$ErrorActionPreference = "Continue"     # each step checks its exit code itself (pip warnings are not errors)
Set-Location -LiteralPath $PSScriptRoot

# 1. Python 3.11 or newer (the pinned packages need it) (the "py" launcher first, then python / python3 on PATH)
$py = $null
foreach ($c in @("py -3", "python", "python3")) {
    $cand = $c -split " "; $exe = $cand[0]; $pre = @($cand | Select-Object -Skip 1)
    if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
    & $exe @pre -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>$null
    if ($LASTEXITCODE -eq 0) { $py = $cand; break }
}
if (-not $py) {
    Write-Host "X  Python 3.11 or newer not found. Install it from https://www.python.org/downloads/ (3.13 recommended,"
    Write-Host "   tick 'Add python.exe to PATH'), then run .\install.ps1 again."
    exit 1
}
$exe = $py[0]; $pre = @($py | Select-Object -Skip 1)
Write-Host ("Python: " + (& $exe @pre --version))

# 2. .venv (created once) + the pinned packages from PyPI
$venvPy = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPy)) {
    Write-Host "Creating .venv ..."
    & $exe @pre -m venv .venv
    if ($LASTEXITCODE -ne 0) { Write-Host "X  Could not create .venv"; exit 1 }
}
Write-Host "Installing packages from requirements-lock.txt (PyPI) ..."
& $venvPy -m pip install --disable-pip-version-check -q -r requirements-lock.txt
if ($LASTEXITCODE -ne 0) { Write-Host "X  pip install failed - check your internet connection, then run .\install.ps1 again"; exit 1 }

# 3. .env from .env.example, only if there is no .env yet (never overwritten, no key written)
& $venvPy -m veda init-env

# 4. The doctor: what is ready, what to fix, which mode VEDA will start in
& $venvPy -m veda doctor

# 5. The server on 127.0.0.1 (not reachable from other computers) + the link
if ($NoStart) { Write-Host "Installed and checked (-NoStart). Start later with: .\install.ps1"; exit 0 }
& $venvPy -m veda start --port $Port
exit $LASTEXITCODE
