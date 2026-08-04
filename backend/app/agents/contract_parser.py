"""Contract/debt agreement parser agent — extracts debt instrument terms from PDF text."""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from dateutil import parser as dateutil_parser

from app.agents.base import AgentError, BaseAgent

logger = logging.getLogger(__name__)

_FACILITY_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\brevolv(?:er|ing credit)\b", re.I), "revolver"),
    (re.compile(r"\bterm\s+loan\b", re.I), "term_loan"),
    (re.compile(r"\bpromissory\s+note\b|\bnote\s+purchase\b", re.I), "note"),
    (re.compile(r"\blease\b|\bASC\s*842\b", re.I), "lease"),
]

_LENDER_RE = re.compile(
    r"(?:^|\n)\s*Lender\s*:\s*(.+?)(?:\s*\(the\s+[\"']?Lender[\"']?\))?$",
    re.I | re.M,
)
_PRINCIPAL_RE = re.compile(
    r"(?:Principal(?:\s+Outstanding)?|Commitment(?:\s+Amount)?)\s*:\s*\$?\s*([\d,]+(?:\.\d+)?)",
    re.I,
)
_RATE_RE = re.compile(
    r"(?:Interest\s+Rate|Rate)\s*:\s*([\d.]+)\s*%",
    re.I,
)
_MATURITY_RE = re.compile(
    r"Maturity(?:\s+Date)?\s*:\s*([^\n\r]+)",
    re.I,
)
_COVENANT_BLOCK_RE = re.compile(
    r"(?:Financial\s+Covenants?|Covenants?)\s*:?\s*(.+?)(?:\n\s*ARTICLE|\n\s*IN WITNESS|\Z)",
    re.I | re.S,
)
_CHANGE_OF_CONTROL_HEADING_RE = re.compile(r"Change\s+(?:of|in)\s+Control\b", re.I)
_PREPAYMENT_HEADING_RE = re.compile(r"\bPrepayment\b", re.I)
_EVENTS_OF_DEFAULT_HEADING_RE = re.compile(r"Events?\s+of\s+Default\b", re.I)
_AFFIRMATIVE_COVENANTS_HEADING_RE = re.compile(
    r"Affirmative\s+Covenants\b|Material\s+Obligations\b", re.I
)
_SECTION_BOUNDARY_RE = re.compile(r"\n\s*ARTICLE\b|\bIN WITNESS\b", re.I)
_ROMAN_ENUM_RE = re.compile(r"\(\s*[ivxlcdm]+\s*\)\s*", re.I)


def extract_debt_heuristics(text: str) -> dict[str, Any]:
    """
    Deterministic extraction of debt terms from agreement text.

    Used as the mock-LLM path so USE_MOCK_LLM=true still grounds results in the
    PDF content instead of inventing filename-based fiction.
    """
    cleaned = (text or "").strip()
    if not cleaned:
        return {"instruments": [], "extraction_confidence": 0.0}

    facility_type = "other"
    for pattern, label in _FACILITY_PATTERNS:
        if pattern.search(cleaned):
            facility_type = label
            break

    lender = _first_group(_LENDER_RE, cleaned)
    if lender:
        lender = re.sub(r"\s+", " ", lender).strip(" .;")

    principal = _parse_money(_first_group(_PRINCIPAL_RE, cleaned))
    rate = _parse_decimal(_first_group(_RATE_RE, cleaned))
    maturity = _parse_date(_first_group(_MATURITY_RE, cleaned))
    covenants = _extract_covenants(cleaned)

    # Core financial terms drive the confidence score. Clause extraction below is enrichment —
    # its presence/absence doesn't dilute confidence in the facility's core economic terms.
    fields = [facility_type != "other", lender, principal, rate, maturity, covenants]
    found = sum(1 for f in fields if f)
    confidence = round(found / len(fields), 2)

    if found == 0:
        return {"instruments": [], "extraction_confidence": 0.0}

    change_of_control = _extract_section_block(cleaned, _CHANGE_OF_CONTROL_HEADING_RE)
    prepayment = _extract_section_block(cleaned, _PREPAYMENT_HEADING_RE)
    events_of_default = _extract_section_block(cleaned, _EVENTS_OF_DEFAULT_HEADING_RE)
    material_obligations = _extract_material_obligations(cleaned)

    instrument: dict[str, Any] = {"facility_type": facility_type}
    if lender:
        instrument["lender"] = lender
    if principal is not None:
        instrument["principal_outstanding"] = f"{principal:.2f}"
    if rate is not None:
        instrument["interest_rate_pct"] = f"{rate:.2f}"
    if maturity is not None:
        instrument["maturity_date"] = maturity.isoformat()
    if covenants:
        instrument["covenants_summary"] = covenants
    if change_of_control:
        instrument["change_of_control_clause"] = change_of_control
    if prepayment:
        instrument["prepayment_terms"] = prepayment
    if events_of_default:
        instrument["events_of_default"] = events_of_default
    if material_obligations:
        instrument["material_obligations"] = material_obligations

    return {
        "instruments": [instrument],
        "extraction_confidence": confidence,
    }


def _first_group(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    if not match:
        return None
    value = match.group(1).strip()
    return value or None


def _parse_money(raw: str | None) -> Decimal | None:
    if not raw:
        return None
    try:
        return Decimal(raw.replace(",", ""))
    except (InvalidOperation, AttributeError):
        return None


def _parse_decimal(raw: str | None) -> Decimal | None:
    if not raw:
        return None
    try:
        return Decimal(raw)
    except (InvalidOperation, AttributeError):
        return None


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return dateutil_parser.parse(raw.strip(), fuzzy=True).date()
    except (ValueError, TypeError, OverflowError):
        return None


def _extract_covenants(text: str) -> str | None:
    # Prefer concrete covenant language with ratios/thresholds over article headers.
    ratio_match = re.search(
        r"((?:Maximum|Max(?:imum)?|Minimum|Min(?:imum)?)\s+"
        r"(?:Net\s+)?(?:Leverage|Interest\s+Coverage|Fixed\s+Charge)[^\n]+)",
        text,
        re.I,
    )
    if ratio_match:
        # Include the following wrapped line if it continues the covenant sentence.
        start = ratio_match.start(1)
        snippet = text[start : start + 280]
        snippet = re.split(r"\n\s*ARTICLE|\n\s*IN WITNESS", snippet, maxsplit=1)[0]
        return re.sub(r"\s+", " ", snippet).strip(" .;")

    match = _COVENANT_BLOCK_RE.search(text)
    if not match:
        return None

    block = match.group(1)
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if re.search(r"shall maintain|following financial covenants", stripped, re.I):
            continue
        if re.search(r"leverage|coverage|reporting", stripped, re.I):
            return re.sub(r"\s+", " ", stripped).strip(" .;")
    cleaned = re.sub(r"\s+", " ", block).strip(" .;")
    return cleaned[:400] if cleaned else None


def _extract_section_block(text: str, heading_pattern: re.Pattern[str]) -> str | None:
    """Extract the prose following a clause heading, up to the next ARTICLE or signature block.

    Grounds change-of-control / prepayment / events-of-default extraction in the actual
    agreement text rather than inventing clause language.
    """
    match = heading_pattern.search(text)
    if not match:
        return None

    remainder = text[match.end():]
    boundary = _SECTION_BOUNDARY_RE.search(remainder)
    block = remainder[: boundary.start()] if boundary else remainder
    cleaned = re.sub(r"\s+", " ", block).strip(" .;:—-")
    return cleaned[:600] if cleaned else None


def _extract_material_obligations(text: str) -> list[str]:
    """Extract an enumerated affirmative-covenant / material-obligation list, e.g. '(i) ... (ii) ...'."""
    block = _extract_section_block(text, _AFFIRMATIVE_COVENANTS_HEADING_RE)
    if not block:
        return []

    # Drop a "The Borrower shall:" style preamble before the first enumerator.
    block = re.sub(r"^.*?shall:\s*", "", block, count=1, flags=re.I)
    parts = _ROMAN_ENUM_RE.split(block)
    return [p.strip(" ;.") for p in parts if p.strip(" ;.")]


class ContractParserAgent(BaseAgent):
    name = "ContractParserAgent"
    # Pinned above the global default: this task's strict tool-schema adherence
    # (nested instrument objects) needs a higher-capability tier than
    # settings.anthropic_model reliably provides — see contract_parser.py's
    # instruments-as-string handling in parse_debt_from_text for the failure
    # mode this was surfacing before the pin.
    model = "claude-opus-5"

    _tools = [
        {
            "name": "extract_debt_instruments",
            "description": "Extract debt facility terms from contract text",
            "input_schema": {
                "type": "object",
                "properties": {
                    "instruments": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "facility_type": {
                                    "type": "string",
                                    "enum": ["term_loan", "revolver", "note", "lease", "other"],
                                },
                                "lender": {"type": "string"},
                                "principal_outstanding": {"type": "string"},
                                "interest_rate_pct": {"type": "string"},
                                "maturity_date": {"type": "string"},
                                "covenants_summary": {"type": "string"},
                                "change_of_control_clause": {"type": "string"},
                                "prepayment_terms": {"type": "string"},
                                "events_of_default": {"type": "string"},
                                "material_obligations": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                            "required": ["facility_type"],
                        },
                    }
                },
                "required": ["instruments"],
            },
        }
    ]

    def _build_messages(self, payload: dict) -> list:
        text = payload.get("text", "")[:12000]
        filename = payload.get("filename", "contract.pdf")
        return [
            {
                "role": "user",
                "content": (
                    f"Extract debt instrument terms from this agreement ({filename}). "
                    f"facility_type must be exactly one of: term_loan, revolver, note, lease, other. "
                    f"Return facility_type, lender, principal_outstanding, interest_rate_pct, "
                    f"maturity_date (YYYY-MM-DD), covenants_summary, change_of_control_clause, "
                    f"prepayment_terms, events_of_default, and material_obligations (list of "
                    f"affirmative covenants/obligations). "
                    f"Return principal_outstanding and interest_rate_pct as plain numbers only "
                    f"(no currency symbols, commas, or percent signs), e.g. \"7500000.00\" and \"7.85\"."
                    f"\n\n{text}"
                ),
            }
        ]

    def _parse_response(self, raw: Any) -> dict:
        if hasattr(raw, "content"):
            for block in raw.content:
                if hasattr(block, "input"):
                    return block.input
        raise AgentError(f"[{self.name}] no tool call in response")

    def _mock_response(self, payload: dict) -> dict:
        """Ground mock extraction in PDF text — never invent terms from the filename alone."""
        text = payload.get("text", "") or ""
        result = extract_debt_heuristics(text)
        if result["instruments"]:
            return result

        filename = payload.get("filename", "contract.pdf")
        logger.warning(
            "[%s] MOCK mode: no debt terms found in text for '%s'",
            self.name,
            filename,
        )
        return {"instruments": [], "extraction_confidence": 0.0}


def _coerce_decimal(raw: Any, *, field: str = "value") -> Decimal | None:
    """Parse an LLM-returned number that may still carry $, commas, or a % sign.
    Logs a warning only when a genuinely-present value fails to parse — a missing/blank
    field is normal and not worth flagging."""
    if raw is None or raw == "":
        return None
    cleaned = re.sub(r"[^\d.\-]", "", str(raw))
    if not cleaned or cleaned in ("-", "."):
        logger.warning("[ContractParserAgent] could not parse %s from LLM output: %r", field, raw)
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        logger.warning("[ContractParserAgent] could not parse %s from LLM output: %r", field, raw)
        return None


_VALID_FACILITY_TYPES = {"term_loan", "revolver", "note", "lease", "other"}


def _coerce_facility_type(raw: Any) -> str:
    """Fall back to 'other' if the LLM returns free text instead of the enum value."""
    if raw is None:
        return "other"
    value = str(raw).strip().lower().replace(" ", "_")
    if value not in _VALID_FACILITY_TYPES:
        logger.warning(
            "[ContractParserAgent] facility_type %r not in %s — defaulting to 'other'",
            raw, sorted(_VALID_FACILITY_TYPES),
        )
        return "other"
    return value


async def parse_debt_from_text(
    deal_id: str,
    text: str,
    source_document: str,
) -> list[dict]:
    """Run contract parser and return normalised instrument dicts."""
    agent = ContractParserAgent()
    result = await agent.run({"text": text, "filename": source_document})
    confidence = float(result.get("extraction_confidence", 0.85))
    raw_instruments = result.get("instruments", [])
    if isinstance(raw_instruments, str):
        # The real model doesn't always perfectly honor the tool's declared
        # input_schema — "instruments" can come back as a JSON-encoded string
        # instead of an actual array. Same class of drift handled defensively
        # in the narrative drafter and red flag analyst.
        try:
            raw_instruments = json.loads(raw_instruments)
        except (json.JSONDecodeError, TypeError):
            logger.warning(
                "[ContractParserAgent] instruments field was a non-JSON string for %s, dropping it",
                source_document,
            )
            raw_instruments = []
    instruments = []
    for item in raw_instruments:
        if not isinstance(item, dict):
            logger.warning(
                "[ContractParserAgent] instrument entry for %s had unexpected shape (%s), skipping",
                source_document, type(item).__name__,
            )
            continue
        maturity = None
        if item.get("maturity_date"):
            try:
                maturity = dateutil_parser.parse(str(item["maturity_date"])).date()
            except (ValueError, TypeError) as exc:
                logger.warning(
                    "[ContractParserAgent] could not parse maturity_date from LLM output: %r (%s)",
                    item["maturity_date"], exc,
                )
                maturity = None
        instruments.append({
            "instrument_id": f"DEBT-{uuid.uuid4().hex[:8].upper()}",
            "deal_id": deal_id,
            "facility_type": _coerce_facility_type(item.get("facility_type")),
            "lender": item.get("lender"),
            "principal_outstanding": _coerce_decimal(
                item.get("principal_outstanding"), field="principal_outstanding"
            ),
            "interest_rate_pct": _coerce_decimal(
                item.get("interest_rate_pct"), field="interest_rate_pct"
            ),
            "maturity_date": maturity,
            "covenants_summary": item.get("covenants_summary"),
            "change_of_control_clause": item.get("change_of_control_clause"),
            "prepayment_terms": item.get("prepayment_terms"),
            "events_of_default": item.get("events_of_default"),
            "material_obligations": item.get("material_obligations") or [],
            "source_document": source_document,
            "extraction_confidence": confidence,
        })
    return instruments
