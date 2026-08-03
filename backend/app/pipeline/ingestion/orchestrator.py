"""
Ingestion stage orchestrator — multi-document data room intake.

Routes uploaded files by document type:
  GL/TB → loader → normalizer → validator
  AR/AP aging → aging parser
  Management projections → projections parser
  PDF debt agreements → pdf extractor → contract parser agent

Persists all artifacts under processed/{deal_id}/.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from app.agents.contract_parser import parse_debt_from_text
from app.pipeline.contracts.pdf_extractor import extract_text_from_bytes
from app.pipeline.ingestion.aging_loader import infer_aging_column_map
from app.pipeline.ingestion.aging_normalizer import normalise_aging
from app.pipeline.ingestion.cross_document_validator import validate_cross_documents
from app.pipeline.ingestion.document_registry import build_inventory
from app.pipeline.ingestion.loader import infer_column_map, load_bytes
from app.pipeline.ingestion.normalizer import normalise
from app.pipeline.ingestion.projections_parser import parse_projections_bytes
from app.pipeline.ingestion.validator import validate
from app.schemas.aging import AgingReport, CrossDocumentValidation
from app.schemas.contracts import DebtInstrument, DebtSchedule
from app.schemas.documents import DocumentInventory, DocumentType
from app.schemas.gl import RawGLLine, ValidationReport
from app.schemas.projections import ProjectionLine, ProjectionSchedule
from app.storage import file_store
from app.storage.json_io import read_json_encrypted, write_json_encrypted

logger = logging.getLogger(__name__)

GL_TYPES = {DocumentType.GENERAL_LEDGER, DocumentType.TRIAL_BALANCE}
AGING_TYPES = {DocumentType.AR_AGING, DocumentType.AP_AGING}


class IngestionError(Exception):
    pass


@dataclass
class IngestionResult:
    gl_lines: list[RawGLLine] = field(default_factory=list)
    validation_report: ValidationReport | None = None
    inventory: DocumentInventory | None = None
    ar_aging: AgingReport | None = None
    ap_aging: AgingReport | None = None
    projections: ProjectionSchedule | None = None
    debt_schedule: DebtSchedule | None = None
    cross_validation: CrossDocumentValidation | None = None
    warnings: list[str] = field(default_factory=list)


def run(deal_id: str) -> IngestionResult:
    """Run full multi-document ingestion for a deal."""
    uploaded = [p for p in file_store.list_uploads(deal_id) if p.is_file() and p.suffix.lower() != ".zip"]
    if not uploaded:
        raise IngestionError(f"No uploaded files found for deal {deal_id}")

    inventory = build_inventory(deal_id, uploaded)
    result = IngestionResult(inventory=inventory)
    all_gl_lines: list[RawGLLine] = []
    ar_summaries = []
    ap_summaries = []
    projection_lines: list[ProjectionLine] = []
    debt_instruments: list[DebtInstrument] = []

    for record in inventory.documents:
        path = Path(record.stored_path)
        try:
            if record.document_type in GL_TYPES:
                lines = _parse_gl(path, deal_id)
                all_gl_lines.extend(lines)
                record.parse_status = "parsed"
                logger.info(
                    "file_parsed filename=%s document_type=%s lines=%d",
                    record.filename, record.document_type, len(lines),
                    extra={"event": "file_parsed", "deal_id": deal_id, "doc_filename": record.filename,
                           "document_type": str(record.document_type), "line_count": len(lines)},
                )
            elif record.document_type == DocumentType.AR_AGING:
                summaries = _parse_aging(path, deal_id, "ar_aging")
                ar_summaries.extend(summaries)
                record.parse_status = "parsed"
                logger.info(
                    "file_parsed filename=%s document_type=%s periods=%d",
                    record.filename, record.document_type, len(summaries),
                    extra={"event": "file_parsed", "deal_id": deal_id, "doc_filename": record.filename,
                           "document_type": str(record.document_type), "period_count": len(summaries)},
                )
            elif record.document_type == DocumentType.AP_AGING:
                summaries = _parse_aging(path, deal_id, "ap_aging")
                ap_summaries.extend(summaries)
                record.parse_status = "parsed"
                logger.info(
                    "file_parsed filename=%s document_type=%s periods=%d",
                    record.filename, record.document_type, len(summaries),
                    extra={"event": "file_parsed", "deal_id": deal_id, "doc_filename": record.filename,
                           "document_type": str(record.document_type), "period_count": len(summaries)},
                )
            elif record.document_type == DocumentType.MANAGEMENT_PROJECTIONS:
                lines = parse_projections_bytes(file_store.read_upload_decrypted(path), path.name, deal_id)
                projection_lines.extend(lines)
                record.parse_status = "parsed"
                logger.info(
                    "file_parsed filename=%s document_type=%s lines=%d",
                    record.filename, record.document_type, len(lines),
                    extra={"event": "file_parsed", "deal_id": deal_id, "doc_filename": record.filename,
                           "document_type": str(record.document_type), "line_count": len(lines)},
                )
            elif record.document_type in {DocumentType.DEBT_AGREEMENT, DocumentType.CONTRACT_OTHER}:
                instruments = _parse_pdf_contract(path, deal_id)
                debt_instruments.extend(instruments)
                if instruments:
                    record.parse_status = "parsed"
                else:
                    record.parse_status = "skipped"
                    record.detail = "PDF text extracted but no debt instrument terms found"
                logger.info(
                    "file_parsed filename=%s document_type=%s instruments=%d",
                    record.filename, record.document_type, len(instruments),
                    extra={"event": "file_parsed", "deal_id": deal_id, "doc_filename": record.filename,
                           "document_type": str(record.document_type), "instrument_count": len(instruments)},
                )
            else:
                record.parse_status = "skipped"
                msg = record.detail or f"Unclassified file skipped: {record.filename}"
                result.warnings.append(msg)
                logger.warning(
                    "file_skipped filename=%s reason=%s",
                    record.filename, msg,
                    extra={"event": "file_skipped", "deal_id": deal_id, "doc_filename": record.filename,
                           "reason": msg},
                )
        except Exception as exc:
            record.parse_status = "failed"
            record.parse_error = str(exc)
            logger.warning(
                "file_parse_failed filename=%s document_type=%s error=%s",
                record.filename, record.document_type, exc,
                extra={"event": "file_parse_failed", "deal_id": deal_id, "doc_filename": record.filename,
                       "document_type": str(record.document_type), "error": str(exc)},
            )
            if record.document_type in GL_TYPES:
                raise IngestionError(f"Failed to ingest GL '{record.filename}': {exc}") from exc

    if not all_gl_lines:
        raise IngestionError(
            f"No GL lines extracted for deal {deal_id}. "
            "Upload a General Ledger or Trial Balance CSV/Excel file."
        )

    report = validate(all_gl_lines, deal_id)
    if not report.is_balanced and not report.is_pl_only_export:
        periods_msg = (
            f" Unbalanced periods: {', '.join(report.unbalanced_periods)}."
            if report.unbalanced_periods
            else ""
        )
        raise IngestionError(
            f"Trial balance does not balance for deal {deal_id}. "
            f"Debits: ${report.total_debits:,.2f} | Credits: ${report.total_credits:,.2f} | "
            f"Difference: ${report.difference:,.2f}.{periods_msg} "
            "Correct the source data before proceeding."
        )

    result.gl_lines = all_gl_lines
    result.validation_report = report

    if ar_summaries:
        result.ar_aging = AgingReport(deal_id=deal_id, document_type="ar_aging", summaries=ar_summaries)
    if ap_summaries:
        result.ap_aging = AgingReport(deal_id=deal_id, document_type="ap_aging", summaries=ap_summaries)
    if projection_lines:
        result.projections = ProjectionSchedule(deal_id=deal_id, lines=projection_lines)
    if debt_instruments:
        result.debt_schedule = DebtSchedule(deal_id=deal_id, instruments=debt_instruments)

    result.cross_validation = validate_cross_documents(
        deal_id, all_gl_lines, result.ar_aging, result.ap_aging
    )

    if inventory.missing_recommended:
        for missing in inventory.missing_recommended:
            result.warnings.append(f"Recommended document not uploaded: {missing}")

    # Merge classification-time warnings (from build_inventory) with parse-time warnings
    # (unclassified skips, missing recommended docs) so document_inventory.json — the
    # only persisted record of file outcomes — carries the full picture, not just the
    # subset known at classification time.
    inventory.warnings = list(dict.fromkeys(inventory.warnings + result.warnings))

    _persist(deal_id, result)

    status_counts: dict[str, int] = {}
    for record in inventory.documents:
        status_counts[record.parse_status] = status_counts.get(record.parse_status, 0) + 1
    logger.info(
        "Ingestion complete for %s: %d GL lines, %d AR, %d AP, %d projections, %d debt instruments "
        "| files: %s",
        deal_id, len(all_gl_lines), len(ar_summaries), len(ap_summaries),
        len(projection_lines), len(debt_instruments), status_counts,
        extra={
            "event": "ingestion_complete", "deal_id": deal_id,
            "gl_line_count": len(all_gl_lines), "ar_period_count": len(ar_summaries),
            "ap_period_count": len(ap_summaries), "projection_line_count": len(projection_lines),
            "debt_instrument_count": len(debt_instruments), "file_status_counts": status_counts,
            "warnings": inventory.warnings,
        },
    )
    return result


def _parse_gl(path: Path, deal_id: str) -> list[RawGLLine]:
    df = load_bytes(file_store.read_upload_decrypted(path), path.name)
    col_map = infer_column_map(df)
    return normalise(df, col_map, path.name, deal_id)


def _parse_aging(path: Path, deal_id: str, doc_type: str) -> list:
    df = load_bytes(file_store.read_upload_decrypted(path), path.name)
    # Detect row-per-invoice (detailed) format and aggregate to summary before normalising
    if "aging bucket" in {c.lower().strip() for c in df.columns}:
        df = _aggregate_detailed_aging(df, path.name)
    col_map = infer_aging_column_map(df, doc_type)
    return normalise_aging(df, col_map, path.name, deal_id, doc_type)


def _aggregate_detailed_aging(df: pd.DataFrame, filename: str) -> pd.DataFrame:
    """Pivot a row-per-invoice aging file into one-summary-row-per-period format.

    Input columns (detected):  As Of Period, Aging Bucket, Total Outstanding / Invoice Amount
    Output columns:            <period_col>, 0-30, 31-60, 61-90, 90+, total
    """
    from app.pipeline.ingestion.loader import LoaderError

    cols_lower = {c.lower().strip(): c for c in df.columns}

    period_col = next(
        (cols_lower[k] for k in ["as of period", "period", "date", "report date"] if k in cols_lower),
        None,
    )
    amount_col = next(
        (cols_lower[k] for k in ["total outstanding", "invoice amount", "amount", "balance"] if k in cols_lower),
        None,
    )
    bucket_col = cols_lower.get("aging bucket")

    if not (period_col and amount_col and bucket_col):
        raise LoaderError(
            f"Detailed aging '{filename}' missing required columns. Found: {list(df.columns)}"
        )

    bucket_name_map: dict[str, str] = {
        "current": "0-30", "1-30 days": "0-30", "0-30": "0-30",
        "31-60 days": "31-60", "31-60": "31-60",
        "61-90 days": "61-90", "61-90": "61-90",
        "90+ days": "90+", "90+": "90+", "over 90": "90+",
        "91+ days": "90+", "91+": "90+",
    }

    work = df.copy()
    work["_bucket"] = work[bucket_col].str.lower().str.strip().map(bucket_name_map)
    work["_amount"] = pd.to_numeric(work[amount_col], errors="coerce").fillna(0)

    agg = (
        work.groupby([period_col, "_bucket"], dropna=False)["_amount"]
        .sum()
        .reset_index()
    )
    pivoted = agg.pivot_table(
        index=period_col, columns="_bucket", values="_amount", aggfunc="sum", fill_value=0
    )
    pivoted.columns.name = None
    pivoted = pivoted.reset_index()

    bucket_cols = [c for c in pivoted.columns if c in {"0-30", "31-60", "61-90", "90+"}]
    pivoted["total"] = pivoted[bucket_cols].sum(axis=1)

    logger.debug(
        "Aggregated detailed aging '%s': %d summary rows from %d detail rows",
        filename, len(pivoted), len(df),
    )
    return pivoted


def _parse_pdf_contract(path: Path, deal_id: str) -> list[DebtInstrument]:
    if path.suffix.lower() != ".pdf":
        return []
    # PdfExtractorError propagates to the caller's per-file try/except, which correctly
    # records parse_status="failed" + parse_error — do not swallow it here, or a genuine
    # extraction failure becomes indistinguishable from an intentional classification skip.
    text = extract_text_from_bytes(file_store.read_upload_decrypted(path), path.name)
    raw_instruments = asyncio.run(parse_debt_from_text(deal_id, text, path.name))
    return [DebtInstrument.model_validate(item) for item in raw_instruments]


def _persist(deal_id: str, result: IngestionResult) -> None:
    processed_dir = file_store.get_processed_dir(deal_id)

    if result.inventory:
        _save_json(result.inventory.model_dump(mode="json"), processed_dir / "document_inventory.json")
    if result.gl_lines:
        _save_json(
            [line.model_dump(mode="json") for line in result.gl_lines],
            processed_dir / "raw_gl.json",
        )
    if result.validation_report:
        _save_json(result.validation_report.model_dump(mode="json"), processed_dir / "validation_report.json")
    if result.ar_aging:
        _save_json(result.ar_aging.model_dump(mode="json"), processed_dir / "ar_aging.json")
    if result.ap_aging:
        _save_json(result.ap_aging.model_dump(mode="json"), processed_dir / "ap_aging.json")
    if result.projections:
        _save_json(result.projections.model_dump(mode="json"), processed_dir / "management_projections.json")
    if result.debt_schedule:
        _save_json(result.debt_schedule.model_dump(mode="json"), processed_dir / "debt_instruments.json")
    if result.cross_validation:
        _save_json(result.cross_validation.model_dump(mode="json"), processed_dir / "cross_document_validation.json")


def _save_json(data, path: Path) -> None:
    write_json_encrypted(path, data)


def load_raw_gl(deal_id: str) -> list[RawGLLine]:
    """Load persisted GL lines from disk."""
    path = file_store.get_processed_dir(deal_id) / "raw_gl.json"
    if not path.exists():
        raise IngestionError(f"No processed GL found for deal {deal_id}. Run ingestion stage first.")
    data = read_json_encrypted(path)
    return [RawGLLine.model_validate(item) for item in data]


def load_document_inventory(deal_id: str) -> DocumentInventory:
    path = file_store.get_processed_dir(deal_id) / "document_inventory.json"
    if not path.exists():
        uploaded = [p for p in file_store.list_uploads(deal_id) if p.is_file() and p.suffix.lower() != ".zip"]
        return build_inventory(deal_id, uploaded)
    return DocumentInventory.model_validate(read_json_encrypted(path))
