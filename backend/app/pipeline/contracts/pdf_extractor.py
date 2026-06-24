"""PDF text extraction for contract/debt agreement parsing."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class PdfExtractorError(Exception):
    pass


def extract_text(path: Path, max_pages: int = 20) -> str:
    """Extract text from a PDF using pdfplumber."""
    try:
        import pdfplumber
    except ImportError as exc:
        raise PdfExtractorError("pdfplumber is not installed") from exc

    if not path.exists():
        raise PdfExtractorError(f"PDF not found: {path}")

    chunks: list[str] = []
    try:
        with pdfplumber.open(path) as pdf:
            for i, page in enumerate(pdf.pages[:max_pages]):
                text = page.extract_text() or ""
                if text.strip():
                    chunks.append(text.strip())
    except Exception as exc:
        raise PdfExtractorError(f"Failed to read PDF '{path.name}': {exc}") from exc

    if not chunks:
        raise PdfExtractorError(f"No extractable text in PDF '{path.name}'")

    full_text = "\n\n".join(chunks)
    logger.info("Extracted %d chars from %s (%d pages)", len(full_text), path.name, len(chunks))
    return full_text
