"""
GL File Loader — accepts CSV or Excel, returns a normalised DataFrame.

Responsibilities:
  - Detect file type by extension (not by content sniffing, which is unreliable)
  - Handle character encoding robustly (UTF-8, Latin-1, CP1252 are all common in
    accounting exports)
  - Return a raw DataFrame with original column names preserved
  - Raise descriptive errors so the operator knows exactly what went wrong

This module does NOT interpret or transform data — that is normalizer.py's job.
"""

import logging
from pathlib import Path

import chardet
import pandas as pd

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".csv", ".xlsx"}


class LoaderError(Exception):
    pass


def load_file(path: str | Path) -> pd.DataFrame:
    """
    Load a GL file from disk into a raw DataFrame.
    Raises LoaderError with a human-readable message on failure.
    """
    p = Path(path)
    if not p.exists():
        raise LoaderError(f"File not found: {p}")

    suffix = p.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise LoaderError(
            f"Unsupported file type '{suffix}'. Accepted: {sorted(SUPPORTED_EXTENSIONS)}"
        )

    logger.info("Loading %s (%s, %.1f KB)", p.name, suffix, p.stat().st_size / 1024)

    try:
        if suffix == ".csv":
            return _load_csv(p)
        else:
            return _load_excel(p)
    except LoaderError:
        raise
    except Exception as exc:
        raise LoaderError(f"Failed to parse '{p.name}': {exc}") from exc


def _load_csv(path: Path) -> pd.DataFrame:
    """Load CSV with automatic encoding detection."""
    raw_bytes = path.read_bytes()

    # Detect encoding from the first 50KB — sufficient for most files
    sample = raw_bytes[:50_000]
    detected = chardet.detect(sample)
    encoding = detected.get("encoding") or "utf-8"
    confidence = detected.get("confidence", 0)

    logger.debug("Detected encoding: %s (confidence %.0f%%)", encoding, confidence * 100)

    # Try detected encoding first; fall back to latin-1 which never raises on any byte
    for enc in [encoding, "utf-8", "latin-1"]:
        try:
            df = pd.read_csv(
                path,
                encoding=enc,
                dtype=str,          # Read everything as string; normalizer handles types
                keep_default_na=False,
                skip_blank_lines=True,
            )
            if df.empty:
                raise LoaderError(f"File '{path.name}' contains no data rows")
            logger.info("Loaded %d rows with encoding '%s'", len(df), enc)
            return df
        except UnicodeDecodeError:
            logger.debug("Encoding '%s' failed, trying next", enc)
            continue

    raise LoaderError(f"Could not decode '{path.name}' with any attempted encoding")


def _load_excel(path: Path) -> pd.DataFrame:
    """Load the first sheet of an Excel file."""
    df = pd.read_excel(
        path,
        sheet_name=0,
        dtype=str,
        keep_default_na=False,
        engine="openpyxl",
    )
    if df.empty:
        raise LoaderError(f"Excel file '{path.name}' contains no data rows")
    logger.info("Loaded %d rows from Excel '%s'", len(df), path.name)
    return df


def infer_column_map(df: pd.DataFrame) -> dict[str, str]:
    """
    Attempt to map raw DataFrame columns to the canonical set:
      date/period, account_code, account_description, debit, credit, amount,
      entity, cost_center, note

    Returns a dict of {raw_column_name: canonical_name}.
    Raises LoaderError if the mandatory columns (date + account + amount) cannot be found.
    """
    cols_lower = {c.lower().strip(): c for c in df.columns}

    def find(candidates: list[str]) -> str | None:
        for cand in candidates:
            if cand in cols_lower:
                return cols_lower[cand]
        return None

    mapping: dict[str, str] = {}

    # Date / Period
    date_col = find(["period", "date", "posting date", "transaction date", "gl date",
                     "accounting date", "post date", "month"])
    if date_col:
        mapping[date_col] = "period"

    # Account code
    code_col = find(["account_code", "account code", "acct code", "acct_code",
                     "gl code", "gl_code", "account number", "account no", "acct no",
                     "account #", "acct #", "code"])
    if code_col:
        mapping[code_col] = "account_code"

    # Account description
    desc_col = find(["account_description", "account description", "acct description",
                     "acct desc", "description", "gl description", "account name",
                     "acct name", "name"])
    if desc_col:
        mapping[desc_col] = "account_description"

    # Amount columns — prefer explicit debit/credit over net amount
    debit_col = find(["debit", "dr", "debit amount", "dr amount"])
    credit_col = find(["credit", "cr", "credit amount", "cr amount"])
    amount_col = find(["amount", "net amount", "net", "value"])

    if debit_col:
        mapping[debit_col] = "debit"
    if credit_col:
        mapping[credit_col] = "credit"
    if amount_col and not (debit_col or credit_col):
        mapping[amount_col] = "amount"

    # Optional columns
    entity_col = find(["entity", "company", "legal entity", "subsidiary", "division"])
    if entity_col:
        mapping[entity_col] = "entity"

    cost_center_col = find(["cost_center", "cost center", "department", "dept",
                             "profit center", "business unit"])
    if cost_center_col:
        mapping[cost_center_col] = "cost_center"

    note_col = find(["note", "notes", "memo", "comment", "comments", "narration",
                     "description2", "remark"])
    if note_col:
        mapping[note_col] = "note"

    # Validation: at minimum we need a date and an account identifier
    if not date_col:
        raise LoaderError(
            "Could not identify a date/period column. "
            f"Available columns: {list(df.columns)}"
        )
    if not code_col and not desc_col:
        raise LoaderError(
            "Could not identify an account code or description column. "
            f"Available columns: {list(df.columns)}"
        )
    if not (debit_col or credit_col or amount_col):
        raise LoaderError(
            "Could not identify a debit, credit, or amount column. "
            f"Available columns: {list(df.columns)}"
        )

    return mapping
