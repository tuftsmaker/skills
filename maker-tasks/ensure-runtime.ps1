# The class Python sandbox (Windows twin of ensure-runtime.sh).
#
# Keep this file pure ASCII. Windows PowerShell 5.1 reads a .ps1 that has no
# BOM as ANSI, so a UTF-8 em dash turns into a smart quote and the parser
# fails with a confusing "missing the terminator" error.
#
# Every class skill runs on this one interpreter - a pinned CPython that uv
# downloads and manages - inside its own venv. The student's own Python is
# never used and never modified, even when it is a matching version.
#
# Run this once per machine; re-running is cheap and repairs a broken sandbox:
#
#     powershell -ExecutionPolicy Bypass -File ensure-runtime.ps1
#
# Its last line is `ENT164_PYTHON=...`: use exactly that interpreter for every
# other command. On Windows it is ~\.venvs\ent164-maker\Scripts\python.exe.

$ErrorActionPreference = "Stop"

$PyVersion = "3.12.14"                 # one pinned interpreter for the class
$PillowVersion = "12.3.0"
$PyYamlVersion = "6.0.3"

if ($env:ENT164_VENV) { $Venv = $env:ENT164_VENV } else { $Venv = Join-Path $HOME ".venvs\ent164-maker" }
if ($env:ENT164_UV) { $Uv = $env:ENT164_UV } else { $Uv = Join-Path $HOME ".local\bin\uv.exe" }

function Say($message) { Write-Host "  $message" }
function Die($message) { Write-Error $message; exit 1 }

if (-not $Venv) { Die "ENT164_VENV is empty" }

# 1. uv, the tool that installs and manages the pinned Python. It is a single
#    user-space binary (never a system package), and UV_NO_MODIFY_PATH tells
#    its installer to leave shell profiles alone - this script calls uv by
#    path, so nothing about the student's shell changes.
if (-not (Test-Path -PathType Leaf $Uv)) {
    Say "installing uv (the Python runtime manager) ..."
    $env:UV_INSTALL_DIR = Split-Path -Parent $Uv
    $env:UV_NO_MODIFY_PATH = "1"
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    if (-not (Test-Path -PathType Leaf $Uv)) { Die "uv did not appear at $Uv" }
}

# 2. The pinned interpreter. `only-managed` is the point: even when the
#    student already has a matching Python, the sandbox gets its own copy.
Say "installing Python $PyVersion ..."
& $Uv python install $PyVersion --python-preference only-managed --quiet
if ($LASTEXITCODE -ne 0) { Die "could not install Python $PyVersion - check your internet connection" }

# 3. The venv. It is rebuilt whenever it is missing, damaged, or was made by
#    some other interpreter (an older version of this skill used the student's
#    Python for it).
$Py = Join-Path $Venv "Scripts\python.exe"
$Mark = Join-Path $Venv ".ent164-python"
$ready = $false
if ((Test-Path -PathType Leaf $Py) -and (Test-Path -PathType Leaf $Mark)) {
    if ((Get-Content $Mark -Raw).Trim() -eq $PyVersion) { $ready = $true }
}
if (-not $ready) {
    if (Test-Path $Venv) {
        Say "replacing the venv at $Venv ..."
        Remove-Item -Recurse -Force $Venv
    } else {
        Say "creating the class venv at $Venv ..."
    }
    $parent = Split-Path -Parent $Venv
    if (-not (Test-Path $parent)) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
    & $Uv venv --seed --python $PyVersion --python-preference only-managed --quiet $Venv
    if ($LASTEXITCODE -ne 0) { Die "could not create the venv at $Venv" }
    Set-Content -Path $Mark -Value $PyVersion
}

# 4. The class packages, pinned as well. Re-running verifies rather than
#    reinstalls; the unpinned fallback covers a wheel disappearing for one
#    platform.
Say "installing Pillow and PyYAML ..."
& $Uv pip install --quiet --python $Py "Pillow==$PillowVersion" "PyYAML==$PyYamlVersion"
if ($LASTEXITCODE -ne 0) {
    & $Uv pip install --quiet --python $Py Pillow PyYAML
    if ($LASTEXITCODE -ne 0) { Die "could not install Pillow and PyYAML - check your internet connection" }
}

& $Py -c "import PIL, yaml"
if ($LASTEXITCODE -ne 0) { Die "the sandbox at $Venv cannot import Pillow and PyYAML - re-run this script" }

Write-Host ""
Write-Host "sandbox : Python $PyVersion at $Venv"
Write-Output "ENT164_PYTHON=$Py"
