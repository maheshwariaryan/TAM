"""Document classification and inventory for data room files."""

import logging
from pathlib import Path

from app.pipeline.ingestion.loader import load_file
from app.schemas.documents import DocumentInventory, DocumentRecord, DocumentType

logger = logging.getLogger(__name__)

GL_EXTENSIONS = {".csv", ".xlsx"}
PDF_EXTENSIONS = {".pdf"}


def classify_by_filename(filename: str) -> tuple[DocumentType, float]:
    """Classify a document from its filename heuristics."""
    name = filename.lower()

    if any(k in name for k in ("ar_aging", "ar aging", "araging", "_ar_", "receivable")):
        return DocumentType.AR_AGING, 0.85
    if any(k in name for k in ("ap_aging", "ap aging", "apaging", "_ap_", "payable")):
        return DocumentType.AP_AGING, 0.85
    if any(k in name for k in ("projection", "forecast", "budget", "mgmt_plan", "management plan")):
        return DocumentType.MANAGEMENT_PROJECTIONS, 0.8
    if any(k in name for k in ("credit_agreement", "loan", "debt", "term_sheet", "revolver", "note")):
        return DocumentType.DEBT_AGREEMENT, 0.8
    if any(k in name for k in ("trial_balance", "trial balance", "_tb_", "tb_")):
        return DocumentType.TRIAL_BALANCE, 0.8
    if any(k in name for k in ("gl_", "_gl", "general_ledger", "general ledger", "ledger")):
        return DocumentType.GENERAL_LEDGER, 0.75
    if name.endswith(".pdf"):
        return DocumentType.CONTRACT_OTHER, 0.5
    if name.endswith((".csv", ".xlsx")):
        return DocumentType.GENERAL_LEDGER, 0.4

    return DocumentType.UNCLASSIFIED, 0.0


def _sniff_columns(path: Path) -> tuple[DocumentType, float]:
    """Refine classification by inspecting column headers."""
    suffix = path.suffix.lower()
    if suffix not in GL_EXTENSIONS:
        return DocumentType.UNCLASSIFIED, 0.0

    try:
        df = load_file(path)
    except Exception:
        return DocumentType.UNCLASSIFIED, 0.0

    cols = {c.lower().strip().replace(" ", "_") for c in df.columns}

    aging_markers = {"0_30", "0-30", "31_60", "31-60", "61_90", "61-90", "90_plus", "90+"}
    if any(m in cols for m in aging_markers) or "bucket" in " ".join(cols):
        if any(k in path.name.lower() for k in ("ap", "payable")):
            return DocumentType.AP_AGING, 0.95
        return DocumentType.AR_AGING, 0.9

    projection_markers = {"revenue", "ebitda", "capex", "forecast", "projection"}
    if len(projection_markers & cols) >= 2:
        return DocumentType.MANAGEMENT_PROJECTIONS, 0.9

    gl_markers = {"account_code", "debit", "credit", "amount", "period", "date"}
    if len(gl_markers & cols) >= 3:
        if any(k in path.name.lower() for k in ("tb", "trial")):
            return DocumentType.TRIAL_BALANCE, 0.9
        return DocumentType.GENERAL_LEDGER, 0.85

    return DocumentType.UNCLASSIFIED, 0.0


def classify_document(path: Path) -> tuple[DocumentType, float]:
    """Combine filename and column heuristics."""
    by_name, name_conf = classify_by_filename(path.name)
    by_cols, col_conf = _sniff_columns(path)

    if col_conf > name_conf:
        return by_cols, col_conf
    return by_name, name_conf


def build_inventory(deal_id: str, file_paths: list[Path]) -> DocumentInventory:
    """Build a document inventory from uploaded file paths."""
    records: list[DocumentRecord] = []
    types_seen: set[DocumentType] = set()

    for path in sorted(file_paths):
        if path.suffix.lower() == ".zip":
            continue
        doc_type, confidence = classify_document(path)
        types_seen.add(doc_type)
        records.append(
            DocumentRecord(
                filename=path.name,
                stored_path=str(path),
                size_bytes=path.stat().st_size,
                document_type=doc_type,
                parse_status="pending",
                confidence=confidence,
            )
        )

    missing: list[str] = []
    has_gl = DocumentType.GENERAL_LEDGER in types_seen or DocumentType.TRIAL_BALANCE in types_seen
    if not has_gl:
        missing.append(DocumentType.GENERAL_LEDGER.value)
    if DocumentType.AR_AGING not in types_seen:
        missing.append(DocumentType.AR_AGING.value)
    if DocumentType.AP_AGING not in types_seen:
        missing.append(DocumentType.AP_AGING.value)

    return DocumentInventory(deal_id=deal_id, documents=records, missing_recommended=missing)
