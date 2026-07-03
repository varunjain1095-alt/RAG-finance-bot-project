"""Fetch remote documents for ingestion."""

import logging

import certifi
import httpx

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (compatible; ICICIPruRAGBot/0.1; +educational-project)"
)


def fetch_url(url: str, timeout: float = 120.0) -> tuple[bytes, str | None]:
    """Return (content_bytes, content_type)."""
    headers = {"User-Agent": USER_AGENT}
    with httpx.Client(
        follow_redirects=True,
        timeout=timeout,
        headers=headers,
        verify=certifi.where(),
    ) as client:
        try:
            response = client.get(url)
        except httpx.ConnectError as exc:
            if "CERTIFICATE_VERIFY_FAILED" not in str(exc):
                raise
            logger.warning("SSL verify failed for %s; retrying without certificate verification", url)
            with httpx.Client(
                follow_redirects=True,
                timeout=timeout,
                headers=headers,
                verify=False,
            ) as insecure_client:
                response = insecure_client.get(url)
        response.raise_for_status()
        content_type = response.headers.get("content-type")
        return response.content, content_type
