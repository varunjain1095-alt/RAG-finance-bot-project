"""FastAPI — health, retrieval debug, chat, learnings, UI."""

import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from rag_bot.config import get_settings
from rag_bot.generation.experience_level import (
    level_acknowledgment,
    should_prompt_experience_level,
)
from rag_bot.generation.learnings import (
    generate_learnings_document,
    get_learnings_pdf_if_fresh,
)
from rag_bot.generation.logging_db import (
    SessionExpiredError,
    create_session,
    get_session_experience_level,
    log_feedback,
    update_session_experience_level,
)
from rag_bot.generation.pipeline import ask
from rag_bot.ingestion.embeddings import verify_embedding_model_startup
from rag_bot.operations.chat_errors import (
    categorize_chat_exception,
    chat_error_detail,
    log_chat_failure,
)
from rag_bot.retrieval.pipeline import retrieve
from rag_bot.ui_config import build_ui_config

logger = logging.getLogger(__name__)

UI_ROOT = Path(__file__).resolve().parents[2] / "ui"

_embedding_model_ready = False


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _embedding_model_ready
    try:
        verify_embedding_model_startup()
    except Exception as exc:
        logger.exception("Startup failed: embedding model could not be loaded")
        raise RuntimeError(
            f"Embedding model startup check failed: {exc}"
        ) from exc
    _embedding_model_ready = True
    logger.info("Startup complete: embedding model verified")
    yield


app = FastAPI(title="ICICI Prudential RAG FAQ Bot", version="0.4.0", lifespan=lifespan)


class RetrieveRequest(BaseModel):
    query: str = Field(..., min_length=1)


class SessionCreateRequest(BaseModel):
    experience_level: str = Field(default="somewhat_familiar")


class ChatRequest(BaseModel):
    session_id: uuid.UUID
    message: str = Field(..., min_length=1)


class FeedbackRequest(BaseModel):
    turn_id: uuid.UUID
    session_id: uuid.UUID
    rating: str = Field(..., pattern="^(thumbs_up|thumbs_down)$")
    comment: str | None = None


@app.get("/")
def root() -> FileResponse:
    return FileResponse(UI_ROOT / "index.html")


@app.get("/health")
def health() -> dict[str, str]:
    if not _embedding_model_ready:
        raise HTTPException(
            status_code=503,
            detail="Embedding model not ready",
        )
    return {"status": "ok", "embedding_model": "ok"}


@app.get("/health/config")
def health_config() -> dict[str, bool]:
    settings = get_settings()
    return {
        "anthropic_api_key_set": bool(settings.anthropic_api_key),
        "voyage_api_key_set": bool(settings.voyage_api_key),
        "database_url_configured": bool(settings.database_url),
        "embedding_model_ready": _embedding_model_ready,
    }


class ExperienceLevelUpdate(BaseModel):
    experience_level: str = Field(..., pattern="^(new|somewhat_familiar|expert)$")


class ExperiencePromptGateRequest(BaseModel):
    message: str = Field(..., min_length=1)


@app.get("/api/ui/config")
def ui_config() -> dict:
    return build_ui_config()


@app.post("/api/ui/experience-prompt-gate")
def experience_prompt_gate(body: ExperiencePromptGateRequest) -> dict[str, bool]:
    return {"prompt_experience_level": should_prompt_experience_level(body.message)}


@app.post("/session")
def create_session_endpoint(body: SessionCreateRequest) -> dict[str, str]:
    session_id = create_session(experience_level=body.experience_level)
    return {
        "session_id": str(session_id),
        "experience_level": get_session_experience_level(session_id),
    }


@app.post("/session/{session_id}/experience-level")
def set_experience_level(session_id: uuid.UUID, body: ExperienceLevelUpdate) -> dict:
    try:
        level = update_session_experience_level(session_id, body.experience_level)
    except SessionExpiredError as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "session_id": str(session_id),
        "experience_level": level,
        "acknowledgment": level_acknowledgment(level),
    }


@app.post("/chat")
def chat(body: ChatRequest) -> dict:
    try:
        result = ask(body.session_id, body.message)
    except SessionExpiredError as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        category = categorize_chat_exception(exc)
        log_chat_failure(
            exc=exc,
            category=category,
            session_id=body.session_id,
            message=body.message,
        )
        raise HTTPException(
            status_code=500,
            detail=chat_error_detail(category),
        ) from exc
    return _ask_result_payload(result)


def _ask_result_payload(result) -> dict:
    return {
        "turn_id": str(result.turn_id),
        "session_id": str(result.session_id),
        "answer": result.answer,
        "refusal_category": result.refusal_category,
        "cited_url": result.cited_url,
        "experience_level": result.experience_level,
        "cost_usd": result.cost_usd,
        "citation_flow": result.citation_flow.to_dict(),
        "timings_ms": {
            "input_filters": result.timings.input_filters_ms,
            "embedding": result.timings.embedding_ms,
            "retrieval": result.timings.retrieval_ms,
            "rerank": result.timings.rerank_ms,
            "generation": result.timings.generation_ms,
            "postprocessing": result.timings.postprocessing_ms,
            "total": result.timings.total_ms,
        },
    }


@app.post("/feedback")
def feedback(body: FeedbackRequest) -> dict[str, str]:
    feedback_id = log_feedback(body.turn_id, body.session_id, body.rating, body.comment)
    return {"feedback_id": str(feedback_id)}


@app.post("/learnings/{session_id}")
def generate_learnings(session_id: uuid.UUID) -> dict[str, str]:
    try:
        path = generate_learnings_document(session_id)
    except SessionExpiredError as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "session_id": str(session_id),
        "download_url": f"/learnings/{session_id}",
        "path": str(path),
    }


@app.get("/learnings/{session_id}")
def download_learnings(session_id: uuid.UUID) -> FileResponse:
    path = get_learnings_pdf_if_fresh(session_id)
    if path is None:
        try:
            path = generate_learnings_document(session_id)
        except SessionExpiredError as exc:
            raise HTTPException(status_code=410, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    return FileResponse(
        path,
        media_type="application/pdf",
        filename="icici_pru_chat_learnings.pdf",
    )


@app.post("/retrieve")
def retrieve_debug(body: RetrieveRequest) -> dict:
    result = retrieve(body.query)
    return {
        "outcome": result.outcome.value,
        "query": result.query,
        "detected_scheme": result.detected_scheme,
        "top_rerank_score": result.top_rerank_score,
        "rerank_used": result.rerank_used,
        "message": result.message,
        "timing_ms": {
            "scheme_detection": result.timing.scheme_detection,
            "expansion": result.timing.expansion,
            "embed": result.timing.embed,
            "retrieval": result.timing.retrieval,
            "rerank": result.timing.rerank,
            "assembly": result.timing.assembly,
            "total": result.timing.total,
        },
        "parents": [
            {
                "parent_chunk_id": p.parent_chunk_id,
                "source_name": p.source_name,
                "source_url": p.source_url,
                "date_version": p.date_version,
                "rerank_score": p.rerank_score,
                "formatted_text": p.formatted_text,
            }
            for p in result.parents
        ],
        "debug": result.debug,
    }


if UI_ROOT.is_dir():
    app.mount("/ui", StaticFiles(directory=str(UI_ROOT), html=True), name="ui")
