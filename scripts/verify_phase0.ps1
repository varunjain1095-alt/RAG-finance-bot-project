# Verify Phase 0: Postgres + pgvector + metabase_readonly role
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Warning "Docker not found in PATH"
}

docker compose up -d postgres
Start-Sleep -Seconds 8

pip install -e . -q
python scripts/verify_phase0.py
