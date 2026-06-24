"""Contract/debt agreement parser agent — extracts debt instrument terms from PDF text."""

import logging
import uuid
from decimal import Decimal
from typing import Any

from dateutil import parser as dateutil_parser

from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class ContractParserAgent(BaseAgent):
    name = "ContractParserAgent"

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
                                "facility_type": {"type": "string"},
                                "lender": {"type": "string"},
                                "principal_outstanding": {"type": "string"},
                                "interest_rate_pct": {"type": "string"},
                                "maturity_date": {"type": "string"},
                                "covenants_summary": {"type": "string"},
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
                    f"Return facility_type, lender, principal_outstanding, interest_rate_pct, "
                    f"maturity_date (YYYY-MM-DD), and covenants_summary.\n\n{text}"
                ),
            }
        ]

    def _parse_response(self, raw: Any) -> dict:
        if hasattr(raw, "content"):
            for block in raw.content:
                if hasattr(block, "input"):
                    return block.input
        return {"instruments": []}

    def _mock_response(self, payload: dict) -> dict:
        filename = payload.get("filename", "contract.pdf")
        is_revolver = "revolver" in filename.lower()
        return {
            "instruments": [
                {
                    "facility_type": "revolver" if is_revolver else "term_loan",
                    "lender": "First National Bank",
                    "principal_outstanding": "4200000.00",
                    "interest_rate_pct": "6.25",
                    "maturity_date": "2028-06-30",
                    "covenants_summary": (
                        "Max leverage 3.5x EBITDA; min fixed charge coverage 1.2x; "
                        "quarterly financial reporting required"
                    ),
                }
            ]
        }


async def parse_debt_from_text(
    deal_id: str,
    text: str,
    source_document: str,
) -> list[dict]:
    """Run contract parser and return normalised instrument dicts."""
    agent = ContractParserAgent()
    result = await agent.run({"text": text, "filename": source_document})
    instruments = []
    for item in result.get("instruments", []):
        maturity = None
        if item.get("maturity_date"):
            try:
                maturity = dateutil_parser.parse(str(item["maturity_date"])).date()
            except (ValueError, TypeError):
                maturity = None
        instruments.append({
            "instrument_id": f"DEBT-{uuid.uuid4().hex[:8].upper()}",
            "deal_id": deal_id,
            "facility_type": item.get("facility_type", "other"),
            "lender": item.get("lender"),
            "principal_outstanding": (
                Decimal(str(item["principal_outstanding"]))
                if item.get("principal_outstanding")
                else None
            ),
            "interest_rate_pct": (
                Decimal(str(item["interest_rate_pct"]))
                if item.get("interest_rate_pct")
                else None
            ),
            "maturity_date": maturity,
            "covenants_summary": item.get("covenants_summary"),
            "source_document": source_document,
            "extraction_confidence": 0.85,
        })
    return instruments
