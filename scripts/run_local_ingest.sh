#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_docker_python_env.sh
source "${SCRIPT_DIR}/_docker_python_env.sh"

ensure_venv_with_packages
"${RAG_VENV}/bin/python" "${SCRIPT_DIR}/apply_migrations.py"
echo "Verifying BGE model is cached..."
"${RAG_VENV}/bin/python" "${SCRIPT_DIR}/download_bge_model.py"
echo "Starting ingestion (local bge-base-en-v1.5, no Voyage)..."
"${RAG_VENV}/bin/python" "${SCRIPT_DIR}/ingest.py"
