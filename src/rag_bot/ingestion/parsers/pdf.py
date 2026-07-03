"""PDF parsing — PyMuPDF primary, pdfplumber for tables, optional OCR."""

import io
import logging
import re

import fitz  # PyMuPDF
import pdfplumber

logger = logging.getLogger(__name__)

OCR_CHAR_THRESHOLD = 100


def _page_to_markdown(text: str, heading: str | None = None) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    body = "\n".join(lines)
    if heading:
        return f"## {heading}\n\n{body}"
    return body


def _ocr_page(page_image_bytes: bytes) -> str:
    try:
        import pytesseract
        from PIL import Image
        import io

        image = Image.open(io.BytesIO(page_image_bytes))
        text = pytesseract.image_to_string(image)
        logger.warning("OCR fallback triggered for PDF page")
        return text
    except Exception as exc:  # noqa: BLE001
        logger.warning("OCR unavailable or failed: %s", exc)
        return ""


def parse_pdf(content: bytes) -> tuple[str, list[str]]:
    """Return (markdown, warnings)."""
    warnings: list[str] = []
    sections: list[str] = []

    doc = fitz.open(stream=content, filetype="pdf")
    try:
        with pdfplumber.open(io.BytesIO(content)) as plumber_doc:
            for i, page in enumerate(doc):
                page_text = page.get_text("text") or ""
                if len(page_text.strip()) < OCR_CHAR_THRESHOLD:
                    pix = page.get_pixmap()
                    ocr_text = _ocr_page(pix.tobytes("png"))
                    if ocr_text.strip():
                        warnings.append(f"page_{i + 1}_ocr")
                        page_text = ocr_text
                if page_text.strip():
                    sections.append(_page_to_markdown(page_text, f"Page {i + 1}"))

                # Supplement with pdfplumber table extraction on same page
                if i < len(plumber_doc.pages):
                    plumber_page = plumber_doc.pages[i]
                    tables = plumber_page.extract_tables() or []
                    for table in tables:
                        if not table:
                            continue
                        if len(table[0]) <= 2:
                            for row in table:
                                if len(row) >= 2 and row[0] and row[1]:
                                    sections.append(f"{row[0].strip()}: {row[1].strip()}.")
                        else:
                            header = table[0]
                            rows = ["| " + " | ".join(cell or "" for cell in header) + " |"]
                            rows.append("| " + " | ".join(["---"] * len(header)) + " |")
                            for row in table[1:]:
                                rows.append("| " + " | ".join(cell or "" for cell in row) + " |")
                            sections.append("\n".join(rows))
    finally:
        doc.close()

    markdown = "\n\n".join(sections)
    markdown = re.sub(r"\n{3,}", "\n\n", markdown).strip()
    return markdown, warnings
