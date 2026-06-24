"""
Red Flag Analyst Agent — enriches rule-detected red flags with:
  - Qualitative context explaining the risk in plain English
  - Specific diligence questions for the deal team
  - Refined financial impact range estimates

Runs concurrently on High-severity flags via asyncio.gather.
Medium flags are enriched only if < 10 total (cost control).
Low/Informational flags use mock enrichment always (not worth the API cost).

Mock: returns templated questions per flag category.
"""

import asyncio
import logging
from typing import Any

from app.agents.base import AgentError, BaseAgent
from app.schemas.redflags import RedFlag

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a Transaction Services Director at a Big 4 firm advising a private
equity buyer on an M&A acquisition. You have been given a list of financial red flags
identified during due diligence of the target company.

For each red flag, provide:
1. A concise qualitative analysis (2-3 sentences) explaining why this is a concern
2. Three specific, actionable diligence questions the deal team should ask management
3. An estimated financial impact range (as a narrative string, e.g. "$200K–$500K annual EBITDA risk")

Focus on the buyer's perspective: what could this mean for future cash flows, valuation,
or deal certainty?"""

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "enrich_redflags",
            "description": "Return enrichment for each red flag.",
            "parameters": {
                "type": "object",
                "properties": {
                    "enrichments": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "flag_id": {"type": "string"},
                                "llm_context": {"type": "string"},
                                "diligence_questions": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "minItems": 3,
                                    "maxItems": 3,
                                },
                                "impact_narrative": {"type": "string"},
                            },
                            "required": ["flag_id", "llm_context", "diligence_questions", "impact_narrative"],
                        },
                    }
                },
                "required": ["enrichments"],
            },
        },
    }
]

# Templated mock questions per flag category
_MOCK_QUESTIONS: dict[str, list[str]] = {
    "Revenue Quality": [
        "Can management provide a breakdown of recurring vs. one-time revenue by customer for the last 3 years?",
        "What contractual protections exist to ensure revenue renewal post-acquisition?",
        "Has the revenue recognition policy changed in the diligence period, and if so, why?",
    ],
    "Cost Structure": [
        "Can management justify the level of owner compensation relative to an arm's-length market rate?",
        "What costs will change structurally following a change of ownership?",
        "Are there any other related-party arrangements not reflected in the GL that should be disclosed?",
    ],
    "Customer Concentration": [
        "What is the contract status, term, and renewal history of the top 3 customers?",
        "Has the business ever lost a major customer, and what was the impact?",
        "Are any key customer contracts subject to change-of-control provisions?",
    ],
    "Cash Flow Quality": [
        "Why does operating cash flow conversion lag EBITDA — is working capital the primary driver?",
        "What is the expected CapEx run-rate post-acquisition vs. the historical level shown?",
        "Has the company utilised any factoring or supply-chain finance arrangements?",
    ],
    "Accounting Policy": [
        "Has there been any change in revenue recognition, depreciation, or accruals policy in the period?",
        "Can management provide the audit management letter for the last two years?",
        "Are there any material provisions or contingent liabilities not reflected in the accounts?",
    ],
}
_DEFAULT_QUESTIONS = [
    "Please provide supporting documentation for the item flagged.",
    "Can management confirm whether this item is expected to recur post-acquisition?",
    "What is the financial impact if this risk crystallises, and is it insurable?",
]


class RedFlagAnalystAgent(BaseAgent):
    name = "RedFlagAnalyst"
    _tools = _TOOLS

    async def enrich(self, flags: list[RedFlag]) -> list[RedFlag]:
        """Enrich a list of flags concurrently. Returns enriched copies."""
        if not flags:
            return []

        # Run each flag as a separate concurrent call (each is an independent analysis)
        tasks = [self.run(flag) for flag in flags]
        enrichments = await asyncio.gather(*tasks, return_exceptions=True)

        enriched: list[RedFlag] = []
        for flag, result in zip(flags, enrichments):
            if isinstance(result, Exception):
                logger.warning("[RedFlagAnalyst] enrichment failed for flag %s: %s", flag.flag_id, result)
                enriched.append(flag)
            else:
                enriched.append(flag.model_copy(update={
                    "llm_context": result.get("llm_context"),
                    "diligence_questions": result.get("diligence_questions", []),
                }))

        return enriched

    def _build_messages(self, payload: RedFlag) -> list[dict]:
        return [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Analyse this red flag and provide enrichment:\n\n"
                    f"Flag ID: {payload.flag_id}\n"
                    f"Severity: {payload.severity}\n"
                    f"Category: {payload.category}\n"
                    f"Title: {payload.title}\n"
                    f"Description: {payload.description}\n"
                    f"Affected Periods: {', '.join(payload.affected_periods[:6])}\n"
                    f"Financial Impact Estimate: "
                    f"${payload.financial_impact_low:,.0f}–${payload.financial_impact_high:,.0f}\n"
                    if payload.financial_impact_low else ""
                    "\nCall enrich_redflags with your analysis."
                ),
            },
        ]

    def _parse_response(self, response: Any) -> dict:
        tool_use = next((b for b in response.content if b.type == "tool_use"), None)
        if not tool_use:
            raise AgentError("[RedFlagAnalyst] no tool call in response")
        data = tool_use.input
        enrichments = data.get("enrichments", [])
        return enrichments[0] if enrichments else {}

    def _mock_response(self, payload: RedFlag) -> dict:
        questions = _MOCK_QUESTIONS.get(payload.category, _DEFAULT_QUESTIONS)
        return {
            "flag_id": payload.flag_id,
            "llm_context": (
                f"[Mock] This {payload.severity.lower()}-severity flag relates to {payload.category}. "
                f"The issue — '{payload.title}' — warrants focused management enquiry "
                f"and independent verification during site visits."
            ),
            "diligence_questions": questions,
            "impact_narrative": "Impact range to be confirmed via management enquiry.",
        }
