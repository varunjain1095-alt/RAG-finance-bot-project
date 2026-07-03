#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_docker_python_env.sh
source "${SCRIPT_DIR}/_docker_python_env.sh"

ensure_venv_with_packages
echo "Verifying BGE model in local cache (safetensors only, no ingestion)..."
"${RAG_VENV}/bin/python" "${SCRIPT_DIR}/download_bge_model.py"
