"""Local embeddings via sentence-transformers (BAAI/bge-base-en-v1.5)."""

import logging
import os
import shutil
from functools import lru_cache
from pathlib import Path

# Disable hf_transfer; large safetensors downloads can stall on HTTP 302 redirects.
os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "0")

from huggingface_hub import snapshot_download
from huggingface_hub.errors import LocalEntryNotFoundError
from sentence_transformers import SentenceTransformer

from rag_bot.config import PROJECT_ROOT

logger = logging.getLogger(__name__)

MODEL_NAME = "BAAI/bge-base-en-v1.5"
EMBEDDING_DIM = 768
DEFAULT_BATCH_SIZE = 32

# Project-local copy avoids broken HF hub symlinks on Windows (WinError 1920).
LOCAL_MODEL_DIR = PROJECT_ROOT / "data" / "models" / "bge-base-en-v1.5"

# sentence-transformers + safetensors only (skip onnx, pytorch_model.bin, etc.)
SAFETENSORS_MODEL_PATTERNS = [
    "model.safetensors",
    "config.json",
    "config_sentence_transformers.json",
    "modules.json",
    "sentence_bert_config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "vocab.txt",
    "1_Pooling/config.json",
]
IGNORE_WEIGHT_ALTERNATES = [
    "onnx/**",
    "**/*.onnx",
    "**/*.bin",
    "**/*.ot",
]

_model_cache_dir: Path | None = None


def _model_files_complete(model_dir: Path) -> bool:
    return (model_dir / "modules.json").exists() and (model_dir / "model.safetensors").exists()


def ensure_embedding_model_downloaded(*, local_files_only: bool = False) -> Path:
    """Resolve model dir; download a full local copy when missing or incomplete."""
    global _model_cache_dir

    if _model_files_complete(LOCAL_MODEL_DIR):
        _model_cache_dir = LOCAL_MODEL_DIR
        return LOCAL_MODEL_DIR

    if local_files_only:
        raise LocalEntryNotFoundError(
            f"Local embedding model incomplete at {LOCAL_MODEL_DIR}"
        )

    LOCAL_MODEL_DIR.parent.mkdir(parents=True, exist_ok=True)
    if LOCAL_MODEL_DIR.exists():
        shutil.rmtree(LOCAL_MODEL_DIR, ignore_errors=True)

    logger.info("Downloading %s to %s (safetensors only)", MODEL_NAME, LOCAL_MODEL_DIR)
    snapshot_download(
        repo_id=MODEL_NAME,
        local_dir=str(LOCAL_MODEL_DIR),
        allow_patterns=SAFETENSORS_MODEL_PATTERNS,
        ignore_patterns=IGNORE_WEIGHT_ALTERNATES,
    )
    _model_cache_dir = LOCAL_MODEL_DIR
    logger.info("Model ready at %s", LOCAL_MODEL_DIR)
    return LOCAL_MODEL_DIR


def _resolve_model_cache_dir() -> Path:
    global _model_cache_dir
    if _model_cache_dir is not None and _model_files_complete(_model_cache_dir):
        return _model_cache_dir
    try:
        return ensure_embedding_model_downloaded(local_files_only=True)
    except LocalEntryNotFoundError:
        logger.warning("Local embedding model missing; downloading %s", MODEL_NAME)
        return ensure_embedding_model_downloaded(local_files_only=False)


@lru_cache(maxsize=1)
def get_embedding_model() -> SentenceTransformer:
    local_dir = _resolve_model_cache_dir()
    logger.info("Loading local embedding model from %s", local_dir)
    try:
        return SentenceTransformer(str(local_dir))
    except OSError as exc:
        logger.warning(
            "Failed to load embedding model from %s (%s); re-downloading",
            local_dir,
            exc,
        )
        get_embedding_model.cache_clear()
        shutil.rmtree(local_dir, ignore_errors=True)
        local_dir = ensure_embedding_model_downloaded(local_files_only=False)
        return SentenceTransformer(str(local_dir))


def embed_texts(
    texts: list[str],
    *,
    batch_size: int | None = None,
    batch_pause_seconds: float | None = None,  # unused; kept for API compatibility
) -> list[list[float]]:
    if not texts:
        return []

    size = batch_size if batch_size is not None else DEFAULT_BATCH_SIZE
    model = get_embedding_model()
    vectors = model.encode(
        texts,
        batch_size=size,
        normalize_embeddings=True,
        show_progress_bar=len(texts) > 64,
    )
    return [row.tolist() for row in vectors]


def verify_embedding_model_startup() -> None:
    """Load BGE and run a probe encode; raises if the model is unusable."""
    logger.info("Verifying embedding model at startup (%s)", LOCAL_MODEL_DIR)
    ensure_embedding_model_downloaded(local_files_only=True)
    model = get_embedding_model()
    dim = model.get_sentence_embedding_dimension()
    if dim != EMBEDDING_DIM:
        raise RuntimeError(
            f"Embedding model dim {dim} != expected {EMBEDDING_DIM}"
        )
    probe = embed_texts(["startup health probe"])
    if not probe or len(probe[0]) != EMBEDDING_DIM:
        raise RuntimeError("Embedding probe returned invalid vector")
    logger.info("Embedding model ready at %s (dim=%d)", LOCAL_MODEL_DIR, EMBEDDING_DIM)
