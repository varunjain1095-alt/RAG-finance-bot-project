#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_docker_python_env.sh
source "${SCRIPT_DIR}/_docker_python_env.sh"

require_venv
echo "Verifying BGE model load (local cache only, no pip, no HF download)..."
"${RAG_VENV}/bin/python" "${SCRIPT_DIR}/download_bge_model.py"
