# Verify BGE model load only — no pip install (requires rag_py_venv populated once).
. "$PSScriptRoot\docker_volumes.ps1"

docker run --rm `
    @DockerEnv `
    @DockerVolumes `
    python:3.12-bookworm `
    bash scripts/run_verify_bge_only.sh
