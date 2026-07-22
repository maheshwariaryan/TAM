"""
Narrative Drafter Agent — drafts the executive-summary-style report sections.

Golden rule enforced harder here than anywhere else in the system: this agent
receives a fact sheet of *already-computed* figures (strings, for display only)
and must only phrase prose around them. It never receives raw GL/financial
data, never performs arithmetic, and is instructed (in both the mock and real
prompt) not to introduce any figure not present in the fact sheet.
"""

import logging
from typing import Any

from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a senior associate at a Big 4 Transaction Advisory Services practice
drafting the narrative sections of a Quality of Earnings report for an M&A buyer.

You will be given a fact sheet of pre-computed figures (already verified by the deterministic
financial engine — you must not recompute or second-guess them). Draft five sections:
executive_summary, key_risks, qoe_highlights, working_capital, recommendations.

RULES:
1. Use ONLY the figures provided in the fact sheet. Never invent, estimate, or infer a number
   that is not explicitly given.
2. If a figure is marked "unavailable" or absent, say so plainly rather than omitting the topic
   silently — the reader must know what could not be assessed.
3. Write in a professional, factual Big 4 tone — no hedging filler, no marketing language.
4. Each section's content should be 2-5 sentences (key_risks and recommendations may use a
   short bulleted list within the text).
"""

_TOOLS = [
    {
        "name": "draft_narrative",
        "description": "Return the drafted narrative sections.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sections": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "section_id": {
                                "type": "string",
                                "enum": [
                                    "executive_summary", "key_risks", "qoe_highlights",
                                    "working_capital", "recommendations",
                                ],
                            },
                            "title": {"type": "string"},
                            "content": {"type": "string"},
                        },
                        "required": ["section_id", "title", "content"],
                    },
                }
            },
            "required": ["sections"],
        },
    }
]


class NarrativeDrafterAgent(BaseAgent):
    name = "NarrativeDrafter"
    _tools = _TOOLS

    def _build_messages(self, payload: dict[str, str]) -> list[dict]:
        fact_lines = "\n".join(f"  {k}: {v}" for k, v in payload.items())
        return [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Fact sheet:\n{fact_lines}\n\n"
                    "Call draft_narrative with the five sections."
                ),
            },
        ]

    def _parse_response(self, raw: Any) -> dict:
        for block in getattr(raw, "content", []):
            if getattr(block, "type", None) == "tool_use":
                return block.input
        return {"sections": []}

    def _mock_response(self, payload: dict[str, str]) -> dict:
        """Deterministic prose built purely from the supplied fact sheet — no LLM call."""
        return {"sections": [s.model_dump() for s in _draft_mock_sections(payload)]}


def _fmt(payload: dict[str, str], key: str, default: str = "unavailable") -> str:
    value = payload.get(key)
    return value if value not in (None, "") else default


def _draft_mock_sections(payload: dict[str, str]) -> list:
    from app.schemas.narrative import NarrativeSection

    revenue = _fmt(payload, "revenue_ltm")
    reported_ebitda = _fmt(payload, "reported_ebitda_ltm")
    adjusted_ebitda = _fmt(payload, "adjusted_ebitda_ltm")
    ebitda_margin = _fmt(payload, "ebitda_margin_pct")
    adj_pct = _fmt(payload, "adjustment_pct")
    high_count = _fmt(payload, "redflag_high_count", "0")
    medium_count = _fmt(payload, "redflag_medium_count", "0")
    top_flags = _fmt(payload, "top_flags", "none identified")
    nwc_peg = _fmt(payload, "nwc_peg_amount")
    nwc_peg_method = _fmt(payload, "nwc_peg_method")
    net_debt = _fmt(payload, "net_debt")
    net_debt_to_ebitda = _fmt(payload, "net_debt_to_ebitda")
    adjustment_count = _fmt(payload, "qoe_adjustment_count", "0")
    adjustment_categories = _fmt(payload, "qoe_categories", "none")
    diligence_questions = _fmt(payload, "diligence_questions", "none outstanding")

    executive_summary = (
        f"LTM revenue is {revenue}, with reported EBITDA of {reported_ebitda} "
        f"({ebitda_margin} margin) and adjusted EBITDA of {adjusted_ebitda} "
        f"after {adj_pct} of QoE adjustments. "
        f"The diligence review identified {high_count} High and {medium_count} Medium severity "
        "red flag(s); see Key Risks below for detail. "
        f"Net debt stands at {net_debt}"
        + (f" ({net_debt_to_ebitda}x LTM EBITDA)." if net_debt_to_ebitda != "unavailable" else ".")
    )

    key_risks = (
        f"{high_count} High and {medium_count} Medium severity red flag(s) were identified. "
        f"Top items: {top_flags}. "
        "Refer to the Red Flag Center for full descriptions, financial impact ranges, and "
        "diligence questions for each item."
    )

    qoe_highlights = (
        f"{adjustment_count} QoE adjustment(s) were identified, totalling {adj_pct} of reported "
        f"EBITDA, moving EBITDA from {reported_ebitda} (reported) to {adjusted_ebitda} (adjusted). "
        f"Adjustment categories: {adjustment_categories}. "
        "Every adjustment retains full source GL line traceability in the QoE Center."
    )

    working_capital = (
        f"The recommended NWC peg is {nwc_peg} ({nwc_peg_method} method)."
        if nwc_peg != "unavailable"
        else "NWC peg is unavailable — AR/AP aging and/or balance sheet data required to compute it."
    )

    recommendations = (
        f"Outstanding diligence questions: {diligence_questions} "
        "Prioritise closing High severity items before final investment committee sign-off; "
        "confirm the recommended NWC peg and net debt figures with the seller's finance team "
        "prior to purchase agreement negotiation."
    )

    return [
        NarrativeSection(section_id="executive_summary", title="Executive Summary", content=executive_summary),
        NarrativeSection(section_id="key_risks", title="Key Risks", content=key_risks),
        NarrativeSection(section_id="qoe_highlights", title="Quality of Earnings Highlights", content=qoe_highlights),
        NarrativeSection(section_id="working_capital", title="Working Capital", content=working_capital),
        NarrativeSection(section_id="recommendations", title="Recommendations", content=recommendations),
    ]
