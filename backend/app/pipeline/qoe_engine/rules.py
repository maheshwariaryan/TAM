"""
QoE Rules Engine — deterministic detection of non-recurring / non-arm's-length items.

Each rule takes the full mapped GL + P&L summary and returns a list of
QoEAdjustment candidates. The LLM reviewer then confirms or rejects each.

Rules implemented:
  LEGAL_SETTLEMENTS       — Full add-back of any Legal Settlements GL category
  MA_TRANSACTION_COSTS    — Full add-back of M&A advisory / due diligence costs
  RELATED_PARTY_EXCESS    — Full add-back of related-party consulting (owner entity fees)
  OWNER_COMP_EXCESS       — Partial add-back: management comp above market benchmark
  RESTRUCTURING           — Full add-back of restructuring charges
  OTHER_NON_RECURRING     — Full add-back of items tagged Other Non-Recurring

Design: rules are pure functions — no side effects, no I/O, no LLM calls.
"""

import logging
import uuid
from datetime import date
from decimal import Decimal

from app.schemas.gl import ChartOfAccountsCategory as CAT
from app.schemas.gl import MappedGLLine
from app.schemas.qoe import QoEAdjustment

logger = logging.getLogger(__name__)

# Market benchmark for management/owner compensation per month.
# Represents a reasonable arm's-length salary for a mid-market CEO/MD.
# Anything above this is flagged as non-arm's-length excess.
OWNER_COMP_MONTHLY_BENCHMARK = Decimal("65000")


def detect_all(
    mapped_lines: list[MappedGLLine],
    deal_id: str,
) -> list[QoEAdjustment]:
    """
    Run all rules and return candidate adjustments.
    Duplicates are impossible because each rule targets distinct categories.
    """
    adjustments: list[QoEAdjustment] = []

    adjustments.extend(_rule_full_addback(
        mapped_lines, deal_id,
        category=CAT.LEGAL_SETTLEMENTS,
        rule_id="LEGAL_SETTLEMENTS",
        label_prefix="Legal Settlement",
        adj_category="One-Time / Non-Recurring",
    ))

    adjustments.extend(_rule_full_addback(
        mapped_lines, deal_id,
        category=CAT.MA_TRANSACTION_COSTS,
        rule_id="MA_TRANSACTION_COSTS",
        label_prefix="M&A Transaction Costs",
        adj_category="One-Time / Non-Recurring",
    ))

    adjustments.extend(_rule_full_addback(
        mapped_lines, deal_id,
        category=CAT.RELATED_PARTY_CONSULTING,
        rule_id="RELATED_PARTY_CONSULTING",
        label_prefix="Related-Party Consulting",
        adj_category="Owner / Related Party",
    ))

    adjustments.extend(_rule_full_addback(
        mapped_lines, deal_id,
        category=CAT.RESTRUCTURING,
        rule_id="RESTRUCTURING",
        label_prefix="Restructuring Charge",
        adj_category="One-Time / Non-Recurring",
    ))

    adjustments.extend(_rule_full_addback(
        mapped_lines, deal_id,
        category=CAT.OTHER_NON_RECURRING,
        rule_id="OTHER_NON_RECURRING",
        label_prefix="Other Non-Recurring Item",
        adj_category="One-Time / Non-Recurring",
    ))

    adjustments.extend(_rule_owner_comp_excess(mapped_lines, deal_id))

    logger.info(
        "QoE rules produced %d candidate adjustments for deal %s",
        len(adjustments), deal_id,
    )
    return adjustments


def _rule_full_addback(
    lines: list[MappedGLLine],
    deal_id: str,
    category: CAT,
    rule_id: str,
    label_prefix: str,
    adj_category: str,
) -> list[QoEAdjustment]:
    """
    Full add-back rule: every GL line in the given category is a candidate
    for complete removal from reported EBITDA.
    Groups by (period, account_description) to produce one adjustment per
    distinct charge rather than one per GL line.
    """
    from collections import defaultdict

    # Group lines by (period, description)
    groups: dict[tuple[date, str], list[MappedGLLine]] = defaultdict(list)
    for line in lines:
        if line.standard_category == category and line.is_ebitda_component:
            groups[(line.period, line.account_description)].append(line)

    adjustments = []
    for (period, desc), group_lines in sorted(groups.items()):
        total = sum(abs(gl.amount) for gl in group_lines)
        if total == 0:
            continue

        adjustments.append(QoEAdjustment(
            adjustment_id=str(uuid.uuid4()),
            deal_id=deal_id,
            period=period,
            label=f"{label_prefix}: {desc}",
            category=adj_category,
            direction="add_back",
            reported_amount=total,
            adjustment_amount=total,
            normalized_amount=Decimal("0"),
            source_gl_line_ids=[gl.line_id for gl in group_lines],
            detection_method="rule",
            rule_triggered=rule_id,
        ))

    return adjustments


def _rule_owner_comp_excess(
    lines: list[MappedGLLine],
    deal_id: str,
) -> list[QoEAdjustment]:
    """
    Owner compensation excess rule.

    For each period, sum all MANAGEMENT_COMPENSATION lines.
    If the total exceeds OWNER_COMP_MONTHLY_BENCHMARK, the excess is flagged
    as a QoE add-back (normalise down to market rate).
    """
    from collections import defaultdict

    period_groups: dict[date, list[MappedGLLine]] = defaultdict(list)
    for line in lines:
        if line.standard_category == CAT.MANAGEMENT_COMPENSATION and line.is_ebitda_component:
            period_groups[line.period].append(line)

    adjustments = []
    for period, group_lines in sorted(period_groups.items()):
        total_comp = sum(abs(gl.amount) for gl in group_lines)
        excess = total_comp - OWNER_COMP_MONTHLY_BENCHMARK

        if excess > Decimal("0.01"):
            adjustments.append(QoEAdjustment(
                adjustment_id=str(uuid.uuid4()),
                deal_id=deal_id,
                period=period,
                label=f"Owner Compensation Normalisation ({period.strftime('%b %Y')})",
                category="Owner / Related Party",
                direction="add_back",
                reported_amount=total_comp,
                adjustment_amount=excess,
                normalized_amount=OWNER_COMP_MONTHLY_BENCHMARK,
                source_gl_line_ids=[gl.line_id for gl in group_lines],
                detection_method="rule",
                rule_triggered="OWNER_COMP_EXCESS",
            ))

    return adjustments
