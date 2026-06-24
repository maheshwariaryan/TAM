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
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from app.agents.contract_parser import parse_debt_from_text
from app.pipeline.contracts.pdf_extractor import PdfExtractorError, extract_text
from app.pipeline.ingestion.aging_loader import infer_aging_column_map
from app.pipeline.ingestion.aging_normalizer import normalise_aging
from app.pipeline.ingestion.cross_document_validator import validate_cross_documents
from app.pipeline.ingestion.document_registry import build_inventory
from app.pipeline.ingestion.loader import infer_column_map, load_file
from app.pipeline.ingestion.normalizer import normalise
from app.pipeline.ingestion.projections_parser import parse_projections
from app.pipeline.ingestion.validator import validate
from app.schemas.aging import AgingReport, CrossDocumentValidation
from app.schemas.contracts import DebtInstrument, DebtSchedule
from app.schemas.documents import DocumentInventory, DocumentType
from app.schemas.gl import RawGLLine, ValidationReport
from app.schemas.projections import ProjectionLine, ProjectionSchedule
from app.storage import file_store

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
            elif record.document_type == DocumentType.AR_AGING:
                ar_summaries.extend(_parse_aging(path, deal_id, "ar_aging"))
                record.parse_status = "parsed"
            elif record.document_type == DocumentType.AP_AGING:
                ap_summaries.extend(_parse_aging(path, deal_id, "ap_aging"))
                record.parse_status = "parsed"
            elif record.document_type == DocumentType.MANAGEMENT_PROJECTIONS:
                projection_lines.extend(parse_projections(path, deal_id))
                record.parse_status = "parsed"
            elif record.document_type in {DocumentType.DEBT_AGREEMENT, DocumentType.CONTRACT_OTHER}:
                instruments = _parse_pdf_contract(path, deal_id)
                debt_instruments.extend(instruments)
                record.parse_status = "parsed" if instruments else "skipped"
            else:
                record.parse_status = "skipped"
                result.warnings.append(f"Unclassified file skipped: {record.filename}")
        except Exception as exc:
            record.parse_status = "failed"
            record.parse_error = str(exc)
            logger.warning("Failed to parse %s: %s", record.filename, exc)
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

    _persist(deal_id, result)
    logger.info(
        "Ingestion complete for %s: %d GL lines, %d AR, %d AP, %d projections, %d debt instruments",
        deal_id, len(all_gl_lines), len(ar_summaries), len(ap_summaries),
        len(projection_lines), len(debt_instruments),
    )
    return result


def _parse_gl(path: Path, deal_id: str) -> list[RawGLLine]:
    df = load_file(path)
    col_map = infer_column_map(df)
    return normalise(df, col_map, path.name, deal_id)


def _parse_aging(path: Path, deal_id: str, doc_type: str) -> list:
    df = load_file(path)
    col_map = infer_aging_column_map(df, doc_type)
    return normalise_aging(df, col_map, path.name, deal_id, doc_type)


def _parse_pdf_contract(path: Path, deal_id: str) -> list[DebtInstrument]:
    if path.suffix.lower() != ".pdf":
        return []
    try:
        text = extract_text(path)
    except PdfExtractorError as exc:
        logger.warning("PDF extraction failed for %s: %s", path.name, exc)
        return []
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
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


def load_raw_gl(deal_id: str) -> list[RawGLLine]:
    """Load persisted GL lines from disk."""
    path = file_store.get_processed_dir(deal_id) / "raw_gl.json"
    if not path.exists():
        raise IngestionError(f"No processed GL found for deal {deal_id}. Run ingestion stage first.")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return [RawGLLine.model_validate(item) for item in data]


def load_document_inventory(deal_id: str) -> DocumentInventory:
    path = file_store.get_processed_dir(deal_id) / "document_inventory.json"
    if not path.exists():
        uploaded = [p for p in file_store.list_uploads(deal_id) if p.is_file() and p.suffix.lower() != ".zip"]
        return build_inventory(deal_id, uploaded)
    with open(path, encoding="utf-8") as f:
        return DocumentInventory.model_validate(json.load(f))
