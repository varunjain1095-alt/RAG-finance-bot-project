# Shared Docker Python env: persistent venv + pip wheel cache on named volumes.
# Mount: -v rag_py_venv:/opt/rag-venv -v rag_pip_cache:/root/.cache/pip

RAG_VENV="${RAG_VENV:-/opt/rag-venv}"
export PIP_CACHE_DIR="${PIP_CACHE_DIR:-/root/.cache/pip}"
export HF_HUB_ENABLE_HF_TRANSFER="${HF_HUB_ENABLE_HF_TRANSFER:-0}"

_venv_has_packages() {
    [[ -x "${RAG_VENV}/bin/python" ]] \
        && "${RAG_VENV}/bin/python" -c "import sentence_transformers" 2>/dev/null
}

ensure_venv_with_packages() {
    if [[ ! -x "${RAG_VENV}/bin/python" ]]; then
        echo "Creating Python venv at ${RAG_VENV}..."
        python -m venv "${RAG_VENV}"
    fi
    if ! _venv_has_packages; then
        echo "Installing rag-bot into venv (pip cache: ${PIP_CACHE_DIR})..."
        "${RAG_VENV}/bin/pip" install -e .
    fi
}

require_venv() {
    if ! _venv_has_packages; then
        echo "FAIL: venv missing or incomplete at ${RAG_VENV}."
        echo "Run once inside Docker with volume mounts:"
        echo "  bash scripts/run_download_bge.sh"
        exit 1
    fi
}
