"""
QoE Reviewer Agent — LLM review of rule-detected adjustment candidates.

For each candidate, Claude/GPT can: accept, reject, or modify the amount.
This creates a human-in-the-loop quality gate even in automated mode.

Mock: accepts all candidates (suitable for development and testing).
Real: sends batches of candidates to GPT with financial context for review.
"""

import logging
from typing import Any

from app.agents.base import AgentError, BaseAgent
from app.schemas.qoe import QoEAdjustment

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a senior Transaction Services Manager at a Big 4 accounting firm
reviewing Quality of Earnings adjustments for an M&A due diligence engagement.

Your task is to review candidate QoE adjustments identified by automated rules and decide:
  - accept: the adjustment is valid and the full amount should be added back
  - reject: the item is recurring or arm's-length and should NOT be adjusted
  - modify: the adjustment is valid but the amount needs changing (provide corrected_amount)

PRINCIPLES:
1. Add back items that are genuinely non-recurring (one-time legal settlements, M&A fees)
2. Add back related-party consulting above arm's-length market rates
3. Normalise owner compensation above a reasonable market salary
4. Do NOT add back items that, despite unusual labels, are recurring operating costs
5. Reject items where the evidence does not support non-recurring treatment

Return structured decisions for every adjustment provided."""

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "review_adjustments",
            "description": "Return accept/reject/modify decisions for each candidate adjustment.",
            "parameters": {
                "type": "object",
                "properties": {
                    "decisions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "adjustment_id": {"type": "string"},
                                "decision": {"type": "string", "enum": ["accept", "reject", "modify"]},
                                "corrected_amount": {
                                    "type": "number",
                                    "description": "Only required when decision=modify"
                                },
                                "reasoning": {"type": "string"},
                                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                            },
                            "required": ["adjustment_id", "decision", "reasoning", "confidence"],
                        },
                    }
                },
                "required": ["decisions"],
            },
        },
    }
]


class QoEReviewerAgent(BaseAgent):
    name = "QoEReviewer"
    _tools = _TOOLS

    async def review(
        self, candidates: list[QoEAdjustment]
    ) -> list[QoEAdjustment]:
        """
        Review candidates and return only accepted/modified adjustments
        with llm_reviewed=True and reasoning populated.
        """
        if not candidates:
            return []

        decisions = await self.run(candidates)
        return _apply_decisions(candidates, decisions)

    def _build_messages(self, payload: list[QoEAdjustment]) -> list[dict]:
        lines = []
        for adj in payload:
            lines.append(
                f"  ID: {adj.adjustment_id}\n"
                f"  Rule: {adj.rule_triggered}\n"
                f"  Label: {adj.label}\n"
                f"  Period: {adj.period}\n"
                f"  Reported Amount: ${adj.reported_amount:,.2f}\n"
                f"  Proposed Add-back: ${adj.adjustment_amount:,.2f}\n"
                f"  Category: {adj.category}\n"
            )
        return [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Review these {len(payload)} QoE adjustment candidates:\n\n"
                    + "\n---\n".join(lines)
                    + "\n\nCall review_adjustments with your decisions."
                ),
            },
        ]

    def _parse_response(self, response: Any) -> list[dict]:
        tool_use = next((b for b in response.content if b.type == "tool_use"), None)
        if not tool_use:
            raise AgentError("[QoEReviewer] no tool call in response")
        return tool_use.input.get("decisions", [])

    def _mock_response(self, payload: list[QoEAdjustment]) -> list[dict]:
        """Mock: accept every candidate — reasonable default for development."""
        return [
            {
                "adjustment_id": adj.adjustment_id,
                "decision": "accept",
                "reasoning": "Mock review: rule-detected adjustment accepted for testing.",
                "confidence": 0.95,
            }
            for adj in payload
        ]


def _apply_decisions(
    candidates: list[QoEAdjustment],
    decisions: list[dict],
) -> list[QoEAdjustment]:
    """Apply accept/reject/modify decisions, returning only accepted adjustments."""
    decision_map = {d["adjustment_id"]: d for d in decisions}
    approved: list[QoEAdjustment] = []

    for adj in candidates:
        dec = decision_map.get(adj.adjustment_id)
        if dec is None:
            logger.warning("No decision for adjustment %s — defaulting to accept", adj.adjustment_id)
            approved.append(adj.model_copy(update={"llm_reviewed": True}))
            continue

        if dec["decision"] == "reject":
            logger.info("Adjustment %s rejected by LLM: %s", adj.adjustment_id, dec["reasoning"])
            continue

        updated: dict = {
            "llm_reviewed": True,
            "llm_reasoning": dec.get("reasoning"),
            "llm_confidence": dec.get("confidence"),
            "analyst_approved": True,
        }
        if dec["decision"] == "modify" and dec.get("corrected_amount") is not None:
            from decimal import Decimal
            updated["adjustment_amount"] = Decimal(str(dec["corrected_amount"]))

        approved.append(adj.model_copy(update=updated))

    logger.info(
        "QoE review: %d candidates → %d accepted (%d rejected)",
        len(candidates), len(approved), len(candidates) - len(approved),
    )
    return approved
