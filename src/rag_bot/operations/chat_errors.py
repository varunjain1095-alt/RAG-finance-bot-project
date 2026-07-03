"""Chat API error categorization and user-safe messaging."""

from __future__ import annotations

import logging
import traceback
from enum import Enum
from typing import Any

import httpx
import psycopg

logger = logging.getLogger(__name__)

CHAT_USER_ERROR_MESSAGE = (
    "Something went wrong while fetching a response. Please try again."
)


class ChatErrorCategory(str, Enum):
    EMBEDDING_RETRIEVAL = "embedding_retrieval"
    DATABASE = "database"
    LLM_GENERATION = "llm_generation"
    UNEXPECTED = "unexpected"


_RETRIEVAL_PATH_MARKERS = (
    "retrieval",
    "embeddings",
    "rerank",
    "ingestion/embeddings",
)
_DB_PATH_MARKERS = (
    "logging_db",
    "ingestion/db",
    "turn_embeddings",
)
_LLM_PATH_MARKERS = (
    "generation/llm",
    "generation/pipeline",
    "generation/citations",
)


def _traceback_module_hint(exc: BaseException) -> ChatErrorCategory | None:
    if not exc.__traceback__:
        return None
    paths = [
        frame.filename.replace("\\", "/").lower()
        for frame in traceback.extract_tb(exc.__traceback__)
    ]
    if any(any(m in p for m in _DB_PATH_MARKERS) for p in paths):
        return ChatErrorCategory.DATABASE
    if any(any(m in p for m in _RETRIEVAL_PATH_MARKERS) for p in paths):
        return ChatErrorCategory.EMBEDDING_RETRIEVAL
    if any(any(m in p for m in _LLM_PATH_MARKERS) for p in paths):
        return ChatErrorCategory.LLM_GENERATION
    return None


def _httpx_error_category(exc: httpx.HTTPError) -> ChatErrorCategory:
    request = getattr(exc, "request", None)
    url = str(getattr(request, "url", "") or "")
    if "anthropic.com" in url:
        return ChatErrorCategory.LLM_GENERATION
    if "voyageai.com" in url:
        return ChatErrorCategory.EMBEDDING_RETRIEVAL
    return ChatErrorCategory.LLM_GENERATION


def categorize_chat_exception(exc: BaseException) -> ChatErrorCategory:
    """Map an exception from ask() to a coarse subsystem category."""
    if isinstance(exc, psycopg.Error):
        return ChatErrorCategory.DATABASE

    if isinstance(exc, httpx.HTTPError):
        return _httpx_error_category(exc)

    if isinstance(exc, OSError):
        return ChatErrorCategory.EMBEDDING_RETRIEVAL

    exc_name = type(exc).__name__
    if exc_name in ("LocalEntryNotFoundError", "RepositoryNotFoundError"):
        return ChatErrorCategory.EMBEDDING_RETRIEVAL

    if isinstance(exc, RuntimeError):
        msg = str(exc).lower()
        if "anthropic" in msg or "api key" in msg:
            return ChatErrorCategory.LLM_GENERATION
        if "embedding" in msg or "sentence_transformers" in msg:
            return ChatErrorCategory.EMBEDDING_RETRIEVAL

    hinted = _traceback_module_hint(exc)
    if hinted is not None:
        return hinted

    return ChatErrorCategory.UNEXPECTED


def log_chat_failure(
    *,
    exc: BaseException,
    category: ChatErrorCategory,
    session_id: Any,
    message: str,
) -> None:
    logger.error(
        "chat failed [%s] session_id=%s user_message=%r: %s",
        category.value,
        session_id,
        message[:500],
        exc,
        exc_info=True,
    )


def chat_error_detail(category: ChatErrorCategory) -> dict[str, str]:
    return {
        "message": CHAT_USER_ERROR_MESSAGE,
        "error_category": category.value,
    }
