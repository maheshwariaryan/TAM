"""
Contract Analysis Orchestrator — on-demand (re-)extraction of debt instrument
terms and clauses from uploaded PDF agreements.

Ingestion already extracts debt instruments as documents are classified and
routed (see pipeline/ingestion/orchestrator.py::_parse_pdf_contract). This
module adds:
  - A standalone POST endpoint to re-run contract analysis (e.g. after
    uploading additional agreements without re-running the full pipeline).
  - A flat ContractClause listing (change-of-control, prepayment, events of
    default, covenants, material obligations) for the Documents/Risk UI,
    built from the same DebtInstrument records so every clause still traces
    back to its source PDF.

Digital (text-extractable) PDFs only — scanned/image PDFs fail extraction
cleanly rather than silently returning nothing.
"""

import asyncio
import logging
from pathlib import Path

from app.agents.contract_parser import parse_debt_from_text
from app.pipeline.contracts.pdf_extractor import PdfExtractorError, extract_text_from_bytes
from app.pipeline.ingestion.orchestrator import load_document_inventory
from app.schemas.contracts import ContractAnalysisReport, ContractClause, DebtInstrument, DebtSchedule
from app.schemas.documents import DocumentType
from app.storage import file_store
from app.storage.json_io import read_json_encrypted, write_json_encrypted

logger = logging.getLogger(__name__)

_CONTRACT_DOC_TYPES = {DocumentType.DEBT_AGREEMENT, DocumentType.CONTRACT_OTHER}

_CLAUSE_FIELD_MAP: list[tuple[str, str]] = [
    ("change_of_control_clause", "change_of_control"),
    ("prepayment_terms", "prepayment"),
    ("events_of_default", "event_of_default"),
    ("covenants_summary", "covenant"),
]


class ContractAnalysisError(Exception):
    pass


def _path(deal_id: str, filename: str) -> Path:
    return file_store.get_processed_dir(deal_id) / filename


def run(deal_id: str) -> ContractAnalysisReport:
    return asyncio.run(_run_async(deal_id))


async def _run_async(deal_id: str) -> ContractAnalysisReport:
    inventory = load_document_inventory(deal_id)
    contract_docs = [d for d in inventory.documents if d.document_type in _CONTRACT_DOC_TYPES]

    if not contract_docs:
        report = ContractAnalysisReport(
            deal_id=deal_id,
            status="skipped",
            message=(
                "No debt agreements or contracts uploaded — upload a PDF credit agreement to "
                "enable contract analysis."
            ),
        )
        _persist(deal_id, report)
        return report

    instruments: list[DebtInstrument] = []
    failures: list[str] = []
    processed_count = 0

    for doc in contract_docs:
        path = Path(doc.stored_path)
        if path.suffix.lower() != ".pdf":
            failures.append(f"{doc.filename}: unsupported file type '{path.suffix}' — only PDF is analyzed")
            logger.warning(
                "Contract analyze: skipping non-PDF contract document %s (type=%s)",
                doc.filename, path.suffix,
                extra={"event": "contract_doc_skipped", "deal_id": deal_id, "doc_filename": doc.filename,
                       "reason": "unsupported_extension"},
            )
            continue
        processed_count += 1
        try:
            text = extract_text_from_bytes(file_store.read_upload_decrypted(path), path.name)
        except PdfExtractorError as exc:
            failures.append(f"{doc.filename}: {exc}")
            logger.warning("Contract analyze: failed to extract text from %s: %s", doc.filename, exc)
            continue
        raw = await parse_debt_from_text(deal_id, text, doc.filename)
        instruments.extend(DebtInstrument.model_validate(item) for item in raw)

    clauses = _build_clauses(instruments)

    # `failures` is always surfaced via extraction_warnings, regardless of whether other
    # documents in the same batch succeeded — a run that extracts 1 of 3 agreements must
    # never look identical to a run that cleanly analyzed all 3.
    if instruments:
        status = "complete"
        message = (
            f"Analyzed {processed_count} of {len(contract_docs)} contract document(s); "
            f"extracted {len(instruments)} instrument(s) and {len(clauses)} clause(s)."
        )
        if failures:
            message += f" {len(failures)} document(s) could not be processed — see extraction_warnings."
    elif failures:
        status = "skipped"
        message = (
            "Contract documents were found but text extraction failed: " + "; ".join(failures) +
            ". This system parses digital (text-extractable) PDFs only — scanned/image PDFs "
            "are not supported."
        )
    else:
        status = "partial"
        message = "Contract documents found but no debt terms could be extracted from the text."

    if failures:
        logger.warning(
            "Contract analyze: %d of %d document(s) failed for deal %s: %s",
            len(failures), len(contract_docs), deal_id, "; ".join(failures),
            extra={"event": "contract_analysis_partial_failure", "deal_id": deal_id,
                   "failure_count": len(failures), "total_documents": len(contract_docs)},
        )

    report = ContractAnalysisReport(
        deal_id=deal_id, status=status, message=message, instruments=instruments, clauses=clauses,
        extraction_warnings=failures,
    )

    if instruments:
        # Keep debt_instruments.json in sync so net_debt_bridge sees re-analyzed data too.
        _save(
            DebtSchedule(deal_id=deal_id, instruments=instruments).model_dump(mode="json"),
            _path(deal_id, "debt_instruments.json"),
        )
    _persist(deal_id, report)
    return report


def _build_clauses(instruments: list[DebtInstrument]) -> list[ContractClause]:
    clauses: list[ContractClause] = []
    for inst in instruments:
        for field, clause_type in _CLAUSE_FIELD_MAP:
            value = getattr(inst, field)
            if value:
                clauses.append(ContractClause(
                    clause_type=clause_type,
                    summary=value,
                    source_document=inst.source_document,
                    instrument_id=inst.instrument_id,
                    confidence=inst.extraction_confidence,
                ))
        for obligation in inst.material_obligations:
            clauses.append(ContractClause(
                clause_type="material_obligation",
                summary=obligation,
                source_document=inst.source_document,
                instrument_id=inst.instrument_id,
                confidence=inst.extraction_confidence,
            ))
    return clauses


def _persist(deal_id: str, report: ContractAnalysisReport) -> None:
    _save(report.model_dump(mode="json"), _path(deal_id, "contract_analysis.json"))


def _save(data: dict, path: Path) -> None:
    write_json_encrypted(path, data)


def load_contract_analysis(deal_id: str) -> ContractAnalysisReport:
    p = _path(deal_id, "contract_analysis.json")
    if p.exists():
        return ContractAnalysisReport.model_validate(read_json_encrypted(p))

    # Fall back to whatever ingestion already produced, so GET works right after a normal
    # /process run without requiring an explicit POST /contracts/analyze call.
    debt_path = _path(deal_id, "debt_instruments.json")
    if not debt_path.exists():
        raise FileNotFoundError(
            f"No contract analysis available for deal {deal_id}. Upload a debt agreement PDF and "
            "run ingestion, or POST /contracts/analyze."
        )
    schedule = DebtSchedule.model_validate(read_json_encrypted(debt_path))
    clauses = _build_clauses(schedule.instruments)
    return ContractAnalysisReport(
        deal_id=deal_id,
        status="complete" if schedule.instruments else "partial",
        message="Derived from ingestion-time contract extraction. POST /contracts/analyze to re-run.",
        instruments=schedule.instruments,
        clauses=clauses,
    )
