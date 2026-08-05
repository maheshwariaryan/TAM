"""
Net Debt Bridge — deterministic net debt from the balance sheet, enriched with
per-instrument contract detail.

Totals (cash, current debt, long-term debt, net debt) are computed purely from
Decimal balance-sheet aggregates — the same audit trail as every other
financial figure in the system. Instrument-level detail (lender, rate,
maturity, covenants) comes from PDF contract extraction and is presented as
supplementary schedule detail; it is never used to recompute the GL-derived
totals, avoiding double-counting between two different sources of truth.
"""

import logging
from decimal import Decimal
from pathlib import Path

from app.schemas.contracts import DebtSchedule
from app.schemas.financials import BalanceSheet, PnLStatement
from app.schemas.gl import ChartOfAccountsCategory as CAT
from app.schemas.net_debt import DebtBridgeComponent, NetDebtInstrumentDetail, NetDebtReport
from app.storage import file_store
from app.storage.json_io import read_json_encrypted, write_json_encrypted

logger = logging.getLogger(__name__)

_RECONCILIATION_TOLERANCE_PCT = Decimal("0.05")  # 5% of total_debt


class NetDebtBridgeError(Exception):
    pass


def _path(deal_id: str, filename: str) -> Path:
    return file_store.get_processed_dir(deal_id) / filename


def _try_load(deal_id: str, filename: str, model_class):
    p = _path(deal_id, filename)
    if not p.exists():
        return None
    return model_class.model_validate(read_json_encrypted(p))


def run(deal_id: str) -> dict:
    bs = _try_load(deal_id, "financials_bs.json", BalanceSheet)
    pnl = _try_load(deal_id, "financials_pnl.json", PnLStatement)
    debt_schedule = _try_load(deal_id, "debt_instruments.json", DebtSchedule)

    report = _build_report(deal_id, bs, pnl, debt_schedule)

    out = _path(deal_id, "net_debt_report.json")
    write_json_encrypted(out, report.model_dump(mode="json"))

    logger.info(
        "Net debt bridge complete for %s (status=%s, net_debt=%s, reconciliation_variance=%s)",
        deal_id, report.status, report.net_debt, report.reconciliation_variance,
    )
    return report.model_dump(mode="json")


def _build_report(
    deal_id: str,
    bs: BalanceSheet | None,
    pnl: PnLStatement | None,
    debt_schedule: DebtSchedule | None,
) -> NetDebtReport:
    if bs is None or not bs.periods:
        return NetDebtReport(
            deal_id=deal_id,
            status="skipped",
            message=(
                "Balance sheet unavailable — net debt bridge requires mapped GL with cash and "
                "debt accounts. Run financial_builder first."
            ),
        )

    latest_period = max(bs.periods)
    pk = latest_period.strftime("%Y-%m")

    def _sum_category(cat: CAT) -> Decimal:
        return sum(
            (r.amount for r in bs.rows if r.category == cat.value and r.period == latest_period),
            Decimal("0"),
        )

    cash = _sum_category(CAT.CASH)
    current_debt = _sum_category(CAT.CURRENT_DEBT)
    long_term_debt = _sum_category(CAT.LONG_TERM_DEBT)
    total_debt = current_debt + long_term_debt
    net_debt = total_debt - cash

    bridge = [
        DebtBridgeComponent(label="Current Portion of Long-Term Debt", amount=current_debt),
        DebtBridgeComponent(label="Long-Term Debt", amount=long_term_debt),
        DebtBridgeComponent(label="Total Debt", amount=total_debt, is_subtotal=True),
        DebtBridgeComponent(label="Less: Cash & Equivalents", amount=-cash),
        DebtBridgeComponent(label="Net Debt", amount=net_debt, is_subtotal=True),
    ]

    net_debt_to_ebitda = None
    if pnl is not None:
        sorted_periods = sorted(pnl.ebitda.keys())
        trailing12 = sorted_periods[-12:] if len(sorted_periods) >= 12 else sorted_periods
        ltm_ebitda = sum((pnl.ebitda[p] for p in trailing12), Decimal("0"))
        if ltm_ebitda > 0:
            net_debt_to_ebitda = float(net_debt / ltm_ebitda)

    instruments: list[NetDebtInstrumentDetail] = []
    instrument_principal_total: Decimal | None = None
    reconciliation_variance = None
    reconciliation_note = None

    if debt_schedule is not None and debt_schedule.instruments:
        instruments = [
            NetDebtInstrumentDetail(
                instrument_id=i.instrument_id,
                facility_type=i.facility_type,
                lender=i.lender,
                principal_outstanding=i.principal_outstanding,
                interest_rate_pct=i.interest_rate_pct,
                maturity_date=i.maturity_date,
                covenants_summary=i.covenants_summary,
                source_document=i.source_document,
                extraction_confidence=i.extraction_confidence,
            )
            for i in debt_schedule.instruments
        ]
        principals = [i.principal_outstanding for i in debt_schedule.instruments if i.principal_outstanding is not None]
        if principals:
            instrument_principal_total = sum(principals, Decimal("0"))
            reconciliation_variance = total_debt - instrument_principal_total
            tolerance = abs(total_debt) * _RECONCILIATION_TOLERANCE_PCT
            within_tolerance = abs(reconciliation_variance) <= tolerance
            if within_tolerance:
                reconciliation_note = (
                    f"Contract-extracted principal (${instrument_principal_total:,.0f}) ties to "
                    f"balance sheet debt (${total_debt:,.0f}) within the 5% tolerance."
                )
            else:
                reconciliation_note = (
                    f"Contract-extracted principal (${instrument_principal_total:,.0f}) differs from "
                    f"balance sheet debt (${total_debt:,.0f}) by ${abs(reconciliation_variance):,.0f}. "
                    "This may reflect facilities not yet drawn, instruments outside the uploaded "
                    "agreements, or amortisation since the agreement date — confirm with the seller."
                )

            log_fn = logger.info if within_tolerance else logger.warning
            log_fn(
                "net_debt_reconciliation deal_id=%s status=%s total_debt=%s "
                "instrument_principal_total=%s variance=%s tolerance=%s",
                deal_id, "Pass" if within_tolerance else "Fail", total_debt,
                instrument_principal_total, reconciliation_variance, tolerance,
                extra={
                    "event": "net_debt_reconciliation", "deal_id": deal_id,
                    "status": "Pass" if within_tolerance else "Fail",
                    "total_debt": str(total_debt),
                    "instrument_principal_total": str(instrument_principal_total),
                    "variance": str(reconciliation_variance), "tolerance": str(tolerance),
                },
            )

    status = "complete" if instruments else "partial"
    message = (
        "Net debt computed from the balance sheet and reconciled against contract-extracted "
        "instrument detail."
        if status == "complete"
        else (
            "Net debt computed from the balance sheet. No debt agreements uploaded — upload PDF "
            "credit agreements to add lender, rate, maturity, and covenant detail."
        )
    )

    return NetDebtReport(
        deal_id=deal_id,
        status=status,
        message=message,
        period=pk,
        cash_and_equivalents=cash,
        current_debt=current_debt,
        long_term_debt=long_term_debt,
        total_debt=total_debt,
        net_debt=net_debt,
        net_debt_to_ebitda=net_debt_to_ebitda,
        bridge=bridge,
        instruments=instruments,
        instrument_principal_total=instrument_principal_total,
        reconciliation_variance=reconciliation_variance,
        reconciliation_note=reconciliation_note,
    )


def load_net_debt_report(deal_id: str) -> NetDebtReport:
    p = _path(deal_id, "net_debt_report.json")
    if not p.exists():
        raise FileNotFoundError(f"Net debt report not found for deal {deal_id}. Run net_debt_bridge stage first.")
    return NetDebtReport.model_validate(read_json_encrypted(p))
