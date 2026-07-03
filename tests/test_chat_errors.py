"""Chat error categorization tests."""

import unittest

import httpx
import psycopg

from rag_bot.operations.chat_errors import (
    ChatErrorCategory,
    categorize_chat_exception,
    chat_error_detail,
)


class ChatErrorCategorizationTests(unittest.TestCase):
    def test_database_operational_error(self) -> None:
        exc = psycopg.OperationalError("connection refused")
        self.assertEqual(
            categorize_chat_exception(exc),
            ChatErrorCategory.DATABASE,
        )

    def test_embedding_oserror(self) -> None:
        exc = OSError(1920, "file cannot be accessed")
        self.assertEqual(
            categorize_chat_exception(exc),
            ChatErrorCategory.EMBEDDING_RETRIEVAL,
        )

    def test_llm_anthropic_http_error(self) -> None:
        request = httpx.Request(
            "POST", "https://api.anthropic.com/v1/messages"
        )
        response = httpx.Response(404, request=request)
        exc = httpx.HTTPStatusError("not found", request=request, response=response)
        self.assertEqual(
            categorize_chat_exception(exc),
            ChatErrorCategory.LLM_GENERATION,
        )

    def test_retrieval_voyage_http_error(self) -> None:
        request = httpx.Request("POST", "https://api.voyageai.com/v1/rerank")
        response = httpx.Response(500, request=request)
        exc = httpx.HTTPStatusError("server error", request=request, response=response)
        self.assertEqual(
            categorize_chat_exception(exc),
            ChatErrorCategory.EMBEDDING_RETRIEVAL,
        )

    def test_llm_runtime_missing_key(self) -> None:
        exc = RuntimeError("ANTHROPIC_API_KEY is not configured")
        self.assertEqual(
            categorize_chat_exception(exc),
            ChatErrorCategory.LLM_GENERATION,
        )

    def test_unexpected_name_error(self) -> None:
        try:
            raise NameError("build_conversation_context is not defined")
        except NameError as exc:
            category = categorize_chat_exception(exc)
        self.assertEqual(category, ChatErrorCategory.UNEXPECTED)

    def test_chat_error_detail_shape(self) -> None:
        detail = chat_error_detail(ChatErrorCategory.DATABASE)
        self.assertEqual(detail["error_category"], "database")
        self.assertIn("Something went wrong", detail["message"])


if __name__ == "__main__":
    unittest.main()
