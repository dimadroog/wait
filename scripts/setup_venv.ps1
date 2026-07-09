# Создание .venv и установка pip-зависимостей из requirements.txt
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$Python = Get-Command python -ErrorAction SilentlyContinue
if (-not $Python) {
    Write-Error "Python не найден. Установите Python 3.10 или 3.11 и добавьте в PATH."
}

$Version = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
$Parts = $Version.Split(".")
$Major = [int]$Parts[0]
$Minor = [int]$Parts[1]
if ($Major -lt 3 -or ($Major -eq 3 -and $Minor -lt 10)) {
    Write-Error "Нужен Python 3.10+, найден $Version"
}

$Venv = Join-Path $RepoRoot ".venv"
if (-not (Test-Path $Venv)) {
    Write-Host "Creating .venv ..."
    & python -m venv $Venv
}

$Pip = Join-Path $Venv "Scripts\pip.exe"
$Py = Join-Path $Venv "Scripts\python.exe"
& $Py -m pip install --upgrade pip
& $Pip install -r (Join-Path $RepoRoot "requirements.txt")

Write-Host "OK: .venv ready. Activate: .\.venv\Scripts\Activate.ps1"
