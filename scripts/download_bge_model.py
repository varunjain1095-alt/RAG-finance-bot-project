"""Verify BAAI/bge-base-en-v1.5 in the Hugging Face cache (safetensors only, no ingestion)."""

import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

from rag_bot.ingestion.embeddings import (
    EMBEDDING_DIM,
    MODEL_NAME,
    ensure_embedding_model_downloaded,
    get_embedding_model,
)


def main() -> int:
    print(f"Verifying {MODEL_NAME} (safetensors only, no onnx/bin)...")
    cache_dir = ensure_embedding_model_downloaded(local_files_only=False)
    print(f"Model dir: {cache_dir}")

    model = get_embedding_model()
    dim = model.get_sentence_embedding_dimension()
    if dim != EMBEDDING_DIM:
        print(f"FAIL: expected dim {EMBEDDING_DIM}, got {dim}")
        return 1
    print(f"Model ready: {MODEL_NAME} (dim={dim})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
