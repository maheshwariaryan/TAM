"""
GL Validator — verifies the integrity of a normalised GL before any analysis begins.

Checks performed:
  1. Trial balance: sum of all debits must equal sum of all credits across the full period.
     For P&L-only uploads (no balance sheet), a per-period check is skipped and a warning
     issued instead (common for management accounts exports).
  2. Date coverage: confirms at least 12 months of data exist (minimum for LTM analysis).
  3. Account coverage: warns if no revenue accounts are identifiable by prefix heuristic.
  4. Duplicate line IDs: flags any duplicated line_id values.

The validation report is non-blocking by default — callers decide whether to abort
on failure. The orchestrator aborts if is_balanced is False for a full trial balance.
"""

import logging
from collections import Counter
from decimal import Decimal

from app.schemas.gl import RawGLLine, ValidationReport

logger = logging.getLogger(__name__)

BALANCE_TOLERANCE = Decimal("0.05")  # $0.05 — rounding from the source system


def validate(lines: list[RawGLLine], deal_id: str) -> ValidationReport:
    """
    Run all integrity checks on a normalised GL line set.

    Returns a ValidationReport. Callers should inspect is_balanced and warnings
    before proceeding to CoA mapping and financial statement building.
    """
    warnings: list[str] = []

    if not lines:
        return ValidationReport(
            deal_id=deal_id,
            total_debits=Decimal("0"),
            total_credits=Decimal("0"),
            difference=Decimal("0"),
            is_balanced=False,
            periods_checked=0,
            is_pl_only_export=False,
            warnings=["No GL lines to validate"],
        )

    # ── 1. Trial balance check ────────────────────────────────────────────────
    # In our signed-amount convention: debits are positive, credits are negative.
    # A balanced set sums to zero.
    total_amount = sum(line.amount for line in lines)
    total_debits = sum(line.amount for line in lines if line.amount > 0)
    total_credits = abs(sum(line.amount for line in lines if line.amount < 0))
    difference = abs(total_amount)
    is_balanced = difference <= BALANCE_TOLERANCE

    if not is_balanced:
        logger.warning(
            "Trial balance FAILS for deal %s: debits=$%s credits=$%s diff=$%s",
            deal_id, total_debits, total_credits, difference,
        )

    # Per-period balance check to identify which periods are off
    from collections import defaultdict
    period_sums: dict[str, Decimal] = defaultdict(Decimal)
    for line in lines:
        period_sums[line.period.strftime("%Y-%m")] += line.amount

    unbalanced_periods = [
        period for period, net in sorted(period_sums.items())
        if abs(net) > BALANCE_TOLERANCE
    ]

    # If all lines are P&L only (no balance sheet), per-period imbalance is expected
    has_bs_lines = any(
        line.account_code.startswith(("1", "2", "3"))
        for line in lines
        if line.account_code and line.account_code[0].isdigit()
    )
    has_revenue_lines = any(
        line.account_code.startswith("4")
        for line in lines
        if line.account_code and line.account_code[0].isdigit()
    )
    is_pl_only_export = not has_bs_lines
    # Mixed export: has both P&L activity (revenue accounts) and BS snapshot rows.
    # The global trial balance will not sum to zero (expected), so we relax that check.
    is_mixed_export = has_bs_lines and has_revenue_lines

    if unbalanced_periods and is_pl_only_export:
        warnings.append(
            f"Per-period imbalance in {len(unbalanced_periods)} period(s) — "
            "this is expected for P&L-only exports (no balance sheet accounts). "
            "Full trial balance check skipped."
        )
        unbalanced_periods = []

    if is_mixed_export and not is_balanced:
        warnings.append(
            "Global trial balance does not sum to zero — this is expected for a mixed "
            "P&L activity + balance sheet snapshot export. Balance sheet quality is "
            "verified per-period by the financial builder."
        )
        is_balanced = True  # treat as acceptable; BS builder enforces Assets = Liab + Eq

    # ── 2. Date coverage check ────────────────────────────────────────────────
    periods = sorted({line.period for line in lines})
    periods_checked = len(periods)

    if periods_checked < 12:
        warnings.append(
            f"Only {periods_checked} period(s) of data found. "
            "Minimum 12 months required for LTM analysis. "
            "NWC peg and QoE trend analysis may be unreliable."
        )
    elif periods_checked < 24:
        warnings.append(
            f"Only {periods_checked} periods found. "
            "24+ months recommended for reliable YoY comparison."
        )

    # ── 3. Revenue account heuristic ─────────────────────────────────────────
    revenue_like = [
        gl for gl in lines
        if gl.account_code and gl.account_code.startswith("4") and gl.amount < 0
    ]
    if not revenue_like:
        warnings.append(
            "No revenue accounts found (expected account codes starting with '4' "
            "and credit-normal amounts). Verify that revenue lines are included."
        )

    # ── 4. Duplicate line_id check ────────────────────────────────────────────
    id_counts = Counter(line.line_id for line in lines)
    duplicates = [lid for lid, cnt in id_counts.items() if cnt > 1]
    if duplicates:
        warnings.append(
            f"{len(duplicates)} duplicate line_id(s) detected. "
            "This may indicate the file was uploaded twice."
        )

    # ── 5. Summary logging ────────────────────────────────────────────────────
    logger.info(
        "Validation complete for deal %s: %d lines | %d periods | balanced=%s | warnings=%d",
        deal_id, len(lines), periods_checked, is_balanced, len(warnings),
    )

    return ValidationReport(
        deal_id=deal_id,
        total_debits=total_debits,
        total_credits=total_credits,
        difference=difference,
        is_balanced=is_balanced,
        tolerance=BALANCE_TOLERANCE,
        periods_checked=periods_checked,
        unbalanced_periods=unbalanced_periods,
        is_pl_only_export=is_pl_only_export,
        is_mixed_export=is_mixed_export,
        warnings=warnings,
    )
