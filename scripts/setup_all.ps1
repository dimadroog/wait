# Phase 0: Python venv
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

& (Join-Path $RepoRoot "scripts\setup_venv.ps1")

Write-Host "Setup complete. FCEUX: fceux/portable/ (вручную или уже на месте)."
