"""PDF text extraction for contract/debt agreement parsing."""

import logging
from io import BytesIO
from pathlib import Path

logger = logging.getLogger(__name__)


class PdfExtractorError(Exception):
    pass


def extract_text(path: Path, max_pages: int = 20) -> str:
    """Extract text from a PDF file on disk (as plaintext bytes).

    This function knows nothing about at-rest encryption — it reads whatever
    bytes are at `path` as literal file content, which is exactly right for
    test fixtures and any other plaintext file. Real uploaded documents are
    encrypted at rest (see app/storage/file_store.py); callers dealing with
    those must decrypt first (file_store.read_upload_decrypted) and call
    extract_text_from_bytes() below with the result — see
    app/pipeline/ingestion/orchestrator.py::_parse_pdf_contract and
    app/pipeline/contracts/orchestrator.py for the production paths.
    """
    if not path.exists():
        raise PdfExtractorError(f"PDF not found: {path}")
    return extract_text_from_bytes(path.read_bytes(), path.name, max_pages=max_pages)


def extract_text_from_bytes(raw_bytes: bytes, filename: str, max_pages: int = 20) -> str:
    """Extract text from already-in-memory PDF bytes (e.g. decrypted upload content)
    using pdfplumber."""
    try:
        import pdfplumber
    except ImportError as exc:
        raise PdfExtractorError("pdfplumber is not installed") from exc

    chunks: list[str] = []
    try:
        with pdfplumber.open(BytesIO(raw_bytes)) as pdf:
            for i, page in enumerate(pdf.pages[:max_pages]):
                text = page.extract_text() or ""
                if text.strip():
                    chunks.append(text.strip())
    except Exception as exc:
        raise PdfExtractorError(f"Failed to read PDF '{filename}': {exc}") from exc

    if not chunks:
        raise PdfExtractorError(f"No extractable text in PDF '{filename}'")

    full_text = "\n\n".join(chunks)
    logger.info("Extracted %d chars from %s (%d pages)", len(full_text), filename, len(chunks))
    return full_text
