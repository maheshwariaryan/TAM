"""Document classification and inventory for data room files."""

import logging
import re
from pathlib import Path

import pandas as pd

from app.pipeline.ingestion.loader import load_bytes
from app.schemas.documents import DocumentInventory, DocumentRecord, DocumentType
from app.storage import file_store

logger = logging.getLogger(__name__)

GL_EXTENSIONS = {".csv", ".xlsx"}
PDF_EXTENSIONS = {".pdf"}

_PERIOD_COL_RE = re.compile(r"^\d{4}-\d{2}$")

# Filename keywords are a FALLBACK only — content is the primary signal (see
# _sniff_schedule_content below). Filenames in a real data room aren't reliable
# (the same report gets renamed constantly), but they're better than nothing
# when a file's content is too sparse/ambiguous to fingerprint confidently.
_SCHEDULE_FILENAME_HINTS: tuple[tuple[DocumentType, tuple[str, ...]], ...] = (
    (DocumentType.DEBT_SCHEDULE, ("debt_schedule", "debt schedule")),
    (DocumentType.WORKING_CAPITAL_SCHEDULE, ("working_capital", "working capital")),
    (DocumentType.INVENTORY_ROLLFORWARD, ("inventory_rollforward", "inventory rollforward")),
    (DocumentType.LEASE_SCHEDULE, ("lease_schedule", "lease schedule")),
    (DocumentType.FIXED_ASSET_REGISTER, ("fixed_asset", "fixed asset")),
    (DocumentType.EQUITY_ROLLFORWARD, ("equity_rollforward", "equity rollforward", "cap_table", "cap table")),
    (DocumentType.PAYROLL_SCHEDULE, ("payroll",)),
    (DocumentType.BANK_STATEMENT, ("bank_statement", "bank statement", "cashbook")),
    (DocumentType.BALANCE_SHEET_SCHEDULE, ("balance_sheet", "balance sheet")),
    (DocumentType.INCOME_STATEMENT_SCHEDULE, ("income_statement", "income statement")),
    (DocumentType.CASH_FLOW_SCHEDULE, ("cash_flow", "cash flow")),
    (DocumentType.REVENUE_SCHEDULE, ("revenue_schedule", "revenue schedule")),
    (DocumentType.COGS_SCHEDULE, ("cogs_schedule", "cogs schedule")),
    (DocumentType.OPEX_SCHEDULE, ("opex_schedule", "opex schedule")),
)


def classify_by_filename(filename: str) -> tuple[DocumentType, float, str | None]:
    """Classify a document from its filename heuristics. Returns (type, confidence, detail)."""
    name = filename.lower()
    suffix = Path(filename).suffix.lower()

    if any(k in name for k in ("ar_aging", "ar aging", "araging", "_ar_", "receivable")):
        return DocumentType.AR_AGING, 0.85, None
    if any(k in name for k in ("ap_aging", "ap aging", "apaging", "_ap_", "payable")):
        return DocumentType.AP_AGING, 0.85, None
    if any(k in name for k in ("projection", "forecast", "budget", "mgmt_plan", "management plan")):
        return DocumentType.MANAGEMENT_PROJECTIONS, 0.8, None
    # Debt agreements are legal documents (PDF only) parsed via LLM — a CSV/XLSX named
    # "debt_schedule" or similar is structured data, handled by the schedule hints below.
    if suffix == ".pdf" and any(
        k in name for k in ("credit_agreement", "loan", "debt", "term_sheet", "revolver", "note")
    ):
        return DocumentType.DEBT_AGREEMENT, 0.8, None
    if any(k in name for k in ("trial_balance", "trial balance", "_tb_", "tb_")):
        return DocumentType.TRIAL_BALANCE, 0.8, None
    if any(k in name for k in ("gl_", "_gl", "general_ledger", "general ledger", "ledger")):
        return DocumentType.GENERAL_LEDGER, 0.75, None

    for doc_type, keywords in _SCHEDULE_FILENAME_HINTS:
        if any(k in name for k in keywords):
            return doc_type, 0.6, None

    if name.endswith(".pdf"):
        return DocumentType.CONTRACT_OTHER, 0.5, None
    if name.endswith((".csv", ".xlsx")):
        return DocumentType.GENERAL_LEDGER, 0.4, None

    return DocumentType.UNCLASSIFIED, 0.0, "Unrecognized file type — filename did not match any known document pattern."


def _normalise_cols(df: pd.DataFrame) -> set[str]:
    return {c.lower().strip().replace(" ", "_") for c in df.columns}


def _sniff_columns(df: pd.DataFrame, filename: str) -> tuple[DocumentType, float]:
    """Refine classification by inspecting column headers (GL/aging/projections only —
    see _sniff_schedule_content for the newer schedule-file signatures)."""
    cols = _normalise_cols(df)

    aging_markers = {"0_30", "0-30", "31_60", "31-60", "61_90", "61-90", "90_plus", "90+"}
    if any(m in cols for m in aging_markers) or "bucket" in " ".join(cols):
        if any(k in filename.lower() for k in ("ap", "payable")):
            return DocumentType.AP_AGING, 0.95
        return DocumentType.AR_AGING, 0.9

    projection_markers = {"revenue", "ebitda", "capex", "forecast", "projection"}
    if len(projection_markers & cols) >= 2:
        return DocumentType.MANAGEMENT_PROJECTIONS, 0.9

    gl_markers = {"account_code", "debit", "credit", "amount", "period", "date"}
    if len(gl_markers & cols) >= 3:
        if any(k in filename.lower() for k in ("tb", "trial")):
            return DocumentType.TRIAL_BALANCE, 0.9
        return DocumentType.GENERAL_LEDGER, 0.85

    return DocumentType.UNCLASSIFIED, 0.0


# Header-keyword signatures for long-format schedules (one row per Period/entity, with
# genuinely distinctive column names — unlike the wide financial-statement schedules below,
# these don't need value-level inspection).
_HEADER_SIGNATURES: tuple[tuple[DocumentType, frozenset[str], int], ...] = (
    (DocumentType.DEBT_SCHEDULE, frozenset({"lender", "loan_type", "maturity", "ending_principal_outstanding"}), 2),
    (DocumentType.WORKING_CAPITAL_SCHEDULE, frozenset({"dso", "dio", "dpo", "nwc"}), 2),
    (DocumentType.INVENTORY_ROLLFORWARD, frozenset({"opening_inventory", "cogs_usage", "ending_inventory"}), 2),
    (DocumentType.LEASE_SCHEDULE, frozenset({"lease_start", "lease_end", "rou_asset_value", "lease_liability"}), 2),
    (DocumentType.FIXED_ASSET_REGISTER, frozenset({"asset_id", "accumulated_depreciation", "net_book_value"}), 2),
    (DocumentType.EQUITY_ROLLFORWARD, frozenset({"shareholder_name", "shares_held", "apic"}), 2),
    (DocumentType.PAYROLL_SCHEDULE, frozenset({"employee_id", "employee_name", "total_compensation"}), 2),
    (DocumentType.BANK_STATEMENT, frozenset({"running_balance", "debit_/_withdrawal", "credit_/_deposit"}), 2),
)

# Label-column VALUE signatures for wide financial statements that all share near-identical
# headers ("Line Item" + period columns) — the label ROW VALUES are what disambiguate them.
_LABEL_VALUE_SIGNATURES: tuple[tuple[DocumentType, frozenset[str]], ...] = (
    (DocumentType.BALANCE_SHEET_SCHEDULE, frozenset({"total assets", "total liabilities", "total equity"})),
    (DocumentType.INCOME_STATEMENT_SCHEDULE, frozenset({"total revenue", "ebitda", "net income", "gross profit"})),
    (DocumentType.CASH_FLOW_SCHEDULE, frozenset({"cash from operations", "cash from financing", "net change in cash"})),
)

_LABEL_COL_CANDIDATES = ("line_item", "account_description", "description")


def _sniff_schedule_content(df: pd.DataFrame, filename: str) -> tuple[DocumentType, float] | None:
    """Content-based classification for the 14 schedule types this pipeline ingests
    beyond GL/aging/projections. Deterministic rule scoring, not ML or an LLM call —
    see document_registry.py module docstring / the ingestion plan for why."""
    cols = _normalise_cols(df)

    # 1) Long-format schedules with distinctive headers.
    best: tuple[DocumentType, float] | None = None
    for doc_type, signature, min_matches in _HEADER_SIGNATURES:
        matches = len(signature & cols)
        if matches >= min_matches:
            confidence = min(0.99, 0.75 + 0.08 * matches)
            if best is None or confidence > best[1]:
                best = (doc_type, confidence)
    if best is not None:
        return best

    # 2) Wide financial statements — disambiguate by label-column values, not headers.
    label_col = next((c for c in df.columns if c.lower().strip().replace(" ", "_") in _LABEL_COL_CANDIDATES), None)
    if label_col is not None:
        values = {str(v).strip().lower() for v in df[label_col].tolist()}
        scored = [
            (doc_type, len(signature & values))
            for doc_type, signature in _LABEL_VALUE_SIGNATURES
        ]
        scored = [s for s in scored if s[1] >= 2]
        if scored:
            scored.sort(key=lambda s: s[1], reverse=True)
            # Require a clear winner — a tie between two statement types means the
            # label values weren't distinctive enough to trust; fall back to filename.
            if len(scored) == 1 or scored[0][1] > scored[1][1]:
                doc_type, matches = scored[0]
                return doc_type, min(0.95, 0.7 + 0.1 * matches)

    # 3) Wide account-level schedules (revenue/cogs/opex) — identical headers
    # ("account_code" + period columns), so the account_code numeric-prefix convention
    # (4xxx=revenue, 5xxx=COGS, 6xxx+=opex) is the only available signal. This convention
    # is common but not universal, so it's treated as moderate-confidence on its own,
    # boosted when the filename agrees — never a hard rule. Gated on having genuine wide
    # period-as-columns shape (>=2 "YYYY-MM" headers) so a normal transaction-row GL file
    # (which also has account_code/account_description, but one "period" column, not many)
    # never gets misread as one of these.
    has_wide_period_columns = sum(1 for c in df.columns if _PERIOD_COL_RE.match(str(c).strip())) >= 2
    if has_wide_period_columns and "account_code" in cols and "account_description" in cols:
        code_col = next(c for c in df.columns if c.lower().strip() == "account_code")
        prefixes = []
        for raw in df[code_col].tolist():
            digits = re.sub(r"\D", "", str(raw))
            if digits:
                prefixes.append(int(digits[0]))
        if prefixes:
            leading_digit = max(set(prefixes), key=prefixes.count)
            doc_type = {4: DocumentType.REVENUE_SCHEDULE, 5: DocumentType.COGS_SCHEDULE}.get(
                leading_digit, DocumentType.OPEX_SCHEDULE if leading_digit >= 6 else None
            )
            if doc_type is not None:
                name = filename.lower()
                name_agrees = any(
                    k in name for dt, keys in _SCHEDULE_FILENAME_HINTS if dt == doc_type for k in keys
                )
                return doc_type, 0.9 if name_agrees else 0.75

    return None


def classify_document(path: Path) -> tuple[DocumentType, float, str | None]:
    """Combine filename and content heuristics — content wins when it fires with
    reasonable confidence; filename is the fallback for sparse/ambiguous files."""
    by_name, name_conf, name_detail = classify_by_filename(path.name)

    if path.suffix.lower() not in GL_EXTENSIONS:
        return by_name, name_conf, name_detail

    try:
        df = load_bytes(file_store.read_upload_decrypted(path), path.name)
    except Exception:
        return by_name, name_conf, name_detail

    by_cols, col_conf = _sniff_columns(df, path.name)
    schedule_result = _sniff_schedule_content(df, path.name)

    candidates = [(by_cols, col_conf)]
    if schedule_result is not None:
        candidates.append(schedule_result)

    best_content_type, best_content_conf = max(candidates, key=lambda c: c[1])
    if best_content_conf > name_conf:
        return best_content_type, best_content_conf, None
    return by_name, name_conf, name_detail


def build_inventory(deal_id: str, file_paths: list[Path]) -> DocumentInventory:
    """Build a document inventory from uploaded file paths."""
    records: list[DocumentRecord] = []
    types_seen: set[DocumentType] = set()
    warnings: list[str] = []

    for path in sorted(file_paths):
        if path.suffix.lower() == ".zip":
            continue
        doc_type, confidence, detail = classify_document(path)
        types_seen.add(doc_type)
        records.append(
            DocumentRecord(
                filename=path.name,
                stored_path=str(path),
                size_bytes=path.stat().st_size,
                document_type=doc_type,
                parse_status="pending",
                confidence=confidence,
                detail=detail,
            )
        )

        if doc_type == DocumentType.UNCLASSIFIED:
            msg = detail or "Unrecognized file — will not be parsed."
            warnings.append(f"{path.name}: {msg}")
            logger.warning(
                "file_classified filename=%s document_type=%s confidence=%.2f detail=%s",
                path.name, doc_type, confidence, msg,
                extra={
                    "event": "file_classified", "deal_id": deal_id, "doc_filename": path.name,
                    "document_type": str(doc_type), "confidence": confidence, "detail": msg,
                },
            )
        else:
            logger.info(
                "file_classified filename=%s document_type=%s confidence=%.2f",
                path.name, doc_type, confidence,
                extra={
                    "event": "file_classified", "deal_id": deal_id, "doc_filename": path.name,
                    "document_type": str(doc_type), "confidence": confidence,
                },
            )

    missing: list[str] = []
    has_gl = DocumentType.GENERAL_LEDGER in types_seen or DocumentType.TRIAL_BALANCE in types_seen
    if not has_gl:
        missing.append(DocumentType.GENERAL_LEDGER.value)
    if DocumentType.AR_AGING not in types_seen:
        missing.append(DocumentType.AR_AGING.value)
    if DocumentType.AP_AGING not in types_seen:
        missing.append(DocumentType.AP_AGING.value)

    logger.info(
        "document_classification_complete deal_id=%s total_files=%d unclassified=%d",
        deal_id, len(records), sum(1 for r in records if r.document_type == DocumentType.UNCLASSIFIED),
        extra={
            "event": "document_classification_complete", "deal_id": deal_id,
            "total_files": len(records),
            "unclassified": sum(1 for r in records if r.document_type == DocumentType.UNCLASSIFIED),
        },
    )

    return DocumentInventory(
        deal_id=deal_id, documents=records, missing_recommended=missing, warnings=warnings,
    )
