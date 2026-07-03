#!/usr/bin/env bash
# Partial re-ingest for specific URLs (no corpus wipe). Usage: bash scripts/run_partial_ingest.sh <url> ...
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_docker_python_env.sh
source "${SCRIPT_DIR}/_docker_python_env.sh"

if [[ $# -eq 0 ]]; then
    echo "Usage: $0 <source_url> ..."
    exit 1
fi

ensure_venv_with_packages
echo "Partial re-ingest ($# URLs, local BGE, no corpus clear)..."
"${RAG_VENV}/bin/python" "${SCRIPT_DIR}/ingest.py" --only-urls "$@"
