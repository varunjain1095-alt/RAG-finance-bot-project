# Standard named volumes for ephemeral python:3.12-bookworm ingest/verify containers.
# rag_py_venv    — persistent venv (packages survive container restarts)
# rag_pip_cache  — pip wheel cache (faster reinstalls into venv)
# rag_bot_hf_cache — Hugging Face model cache

$ProjectRoot = Split-Path -Parent $PSScriptRoot

$DockerVolumes = @(
    "-v", "rag_py_venv:/opt/rag-venv",
    "-v", "rag_pip_cache:/root/.cache/pip",
    "-v", "rag_bot_hf_cache:/root/.cache/huggingface",
    "-v", "${ProjectRoot}:/app",
    "-w", "/app"
)

$DockerEnv = @(
    "-e", "HF_HUB_ENABLE_HF_TRANSFER=0",
    "-e", "PIP_CACHE_DIR=/root/.cache/pip"
)
