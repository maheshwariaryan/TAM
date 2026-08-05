"""Automated multi-tab Excel databook generator."""

import logging
from datetime import UTC, datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from app.storage import deal_store, file_store
from app.storage.json_io import try_read_json_encrypted

logger = logging.getLogger(__name__)

HEADER_FILL = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
HEADER_FONT = Font(color="FFFFFF", bold=True)


class DatabookError(Exception):
    pass


def _load_json(path: Path) -> dict | list | None:
    return try_read_json_encrypted(path)


def _style_header(ws, row: int, col_count: int) -> None:
    for col in range(1, col_count + 1):
        cell = ws.cell(row=row, column=col)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT


def _write_table(ws, headers: list[str], rows: list[list], start_row: int = 1) -> int:
    for col, h in enumerate(headers, 1):
        ws.cell(row=start_row, column=col, value=h)
    _style_header(ws, start_row, len(headers))
    for i, row in enumerate(rows, start_row + 1):
        for col, val in enumerate(row, 1):
            ws.cell(row=i, column=col, value=val)
    for col in range(1, len(headers) + 1):
        ws.column_dimensions[get_column_letter(col)].width = 18
    return start_row + len(rows) + 2


def generate(deal_id: str) -> bytes:
    """Build a multi-tab Excel databook and return bytes."""
    deal = deal_store.get_deal(deal_id)
    if deal is None:
        raise DatabookError(f"Deal {deal_id} not found")

    processed = file_store.get_processed_dir(deal_id)
    qoe = _load_json(processed / "qoe_report.json")
    if not qoe:
        raise DatabookError("QoE report not found. Run the full pipeline before exporting databook.")

    wb = Workbook()
    wb.remove(wb.active)

    # Cover
    cover = wb.create_sheet("Cover")
    cover["A1"] = "FDD Databook"
    cover["A2"] = f"Company: {deal['company_name']}"
    cover["A3"] = f"Deal: {deal['deal_name']}"
    cover["A4"] = f"Currency: {deal['currency']}"
    cover["A5"] = f"Generated: {datetime.now(UTC).isoformat()}"

    # QoE Waterfall
    wf = wb.create_sheet("QoE Waterfall")
    wf_rows = []
    for item in qoe.get("waterfall", []):
        wf_rows.append([item.get("label"), item.get("amount"), item.get("type")])
    next_row = _write_table(wf, ["Label", "Amount", "Type"], wf_rows)

    # Normalized EBITDA formula row
    amounts = [Decimal(str(r[1])) for r in wf_rows if r[1] is not None]
    if amounts:
        wf.cell(row=next_row, column=1, value="Check: Waterfall terminal")
        wf.cell(row=next_row, column=2, value=str(sum(amounts)))
    else:
        logger.warning(
            "Databook: QoE Waterfall terminal check row omitted for deal %s — "
            "no amounts present in the waterfall data",
            deal_id,
        )

    # Adjustment Ledger
    adj_sheet = wb.create_sheet("Adjustment Ledger")
    adj_rows = []
    for adj in qoe.get("adjustments", []):
        adj_rows.append([
            adj.get("adjustment_id"),
            adj.get("label"),
            adj.get("category"),
            adj.get("direction"),
            adj.get("adjustment_amount"),
            ", ".join(adj.get("source_gl_line_ids", [])),
        ])
    _write_table(
        adj_sheet,
        ["ID", "Label", "Category", "Direction", "Amount", "Source GL Lines"],
        adj_rows,
    )

    # GL Mapping
    mapped = _load_json(processed / "mapped_gl.json")
    if mapped:
        map_sheet = wb.create_sheet("GL Mapping")
        seen: dict[str, list] = {}
        for line in mapped:
            code = line.get("account_code", "")
            if code not in seen:
                seen[code] = [
                    code,
                    line.get("account_description"),
                    line.get("standard_category"),
                    line.get("financial_statement"),
                ]
        _write_table(
            map_sheet,
            ["Account Code", "Description", "Category", "Statement"],
            list(seen.values()),
        )
    else:
        logger.warning(
            "Databook: 'GL Mapping' sheet omitted for deal %s — mapped_gl.json not found "
            "(run coa_mapping/financial_builder first)",
            deal_id,
        )

    # Financials tabs
    for fname, title in [
        ("financials_pnl.json", "P&L"),
        ("financials_bs.json", "Balance Sheet"),
        ("financials_cf.json", "Cash Flow"),
    ]:
        data = _load_json(processed / fname)
        if not data:
            logger.warning(
                "Databook: '%s' sheet omitted for deal %s — %s not found "
                "(likely a P&L-only deal, or financial_builder hasn't run)",
                title, deal_id, fname,
            )
            continue
        sheet = wb.create_sheet(title)
        rows = data.get("rows", [])
        if rows:
            headers = list(rows[0].keys()) if rows else []
            table_rows = [[r.get(h) for h in headers] for r in rows]
            _write_table(sheet, headers, table_rows)

    # NWC Trend + Pegs
    nwc = _load_json(processed / "nwc_report.json")
    if not nwc or not nwc.get("data_points"):
        logger.warning(
            "Databook: 'NWC Trend'/'NWC Pegs' sheets omitted for deal %s — nwc_report.json "
            "not found or has no data points (nwc_analyzer hasn't run, or no balance sheet)",
            deal_id,
        )
    else:
        nwc_sheet = wb.create_sheet("NWC Trend")
        nwc_rows = [
            [
                dp.get("period"), str(dp.get("accounts_receivable")), str(dp.get("inventory")),
                str(dp.get("prepaid_expenses")), str(dp.get("other_current_assets")),
                str(dp.get("accounts_payable")), str(dp.get("accrued_liabilities")),
                str(dp.get("deferred_revenue")), str(dp.get("current_debt")),
                str(dp.get("other_current_liabilities")), str(dp.get("net_working_capital")),
                dp.get("nwc_as_pct_revenue"),
            ]
            for dp in nwc["data_points"]
        ]
        next_row = _write_table(
            nwc_sheet,
            ["Period", "AR", "Inventory", "Prepaid Exp", "Other CA", "AP", "Accrued Liab",
             "Deferred Rev", "Current Debt", "Other CL", "NWC", "NWC % Revenue"],
            nwc_rows,
        )
        ratios = nwc.get("ratios") or {}
        if ratios:
            nwc_sheet.cell(row=next_row, column=1, value=f"Ratios ({ratios.get('period')})")
            nwc_sheet.cell(row=next_row + 1, column=1, value="DSO / DPO / DIO / CCC (days)")
            nwc_sheet.cell(row=next_row + 1, column=2, value=(
                f"{ratios.get('dso_days')} / {ratios.get('dpo_days')} / "
                f"{ratios.get('dio_days')} / {ratios.get('cash_conversion_cycle_days')}"
            ))
            nwc_sheet.cell(row=next_row + 2, column=1, value="AR / AP > 60d %")
            nwc_sheet.cell(row=next_row + 2, column=2, value=(
                f"{ratios.get('ar_over_60d_pct')} / {ratios.get('ap_over_60d_pct')}"
            ))

        peg_sheet = wb.create_sheet("NWC Pegs")
        peg_rows = [
            [
                p.get("method"), str(p.get("peg_amount")),
                str(p.get("confidence_interval_low")), str(p.get("confidence_interval_high")),
                "Yes" if p.get("recommended") else "No",
                "Yes" if p.get("seasonality_detected") else "No",
                p.get("rationale"),
            ]
            for p in nwc.get("pegs", [])
        ]
        _write_table(
            peg_sheet,
            ["Method", "Peg Amount", "CI Low", "CI High", "Recommended", "Seasonality", "Rationale"],
            peg_rows,
        )

    # Net Debt Bridge
    net_debt = _load_json(processed / "net_debt_report.json")
    if not net_debt or not net_debt.get("bridge"):
        logger.warning(
            "Databook: 'Net Debt' sheet omitted for deal %s — net_debt_report.json not found "
            "or has no bridge (net_debt_bridge hasn't run, or no balance sheet)",
            deal_id,
        )
    else:
        nd_sheet = wb.create_sheet("Net Debt")
        nd_sheet.cell(row=1, column=1, value=f"As of {net_debt.get('period')}")
        nd_sheet.cell(row=2, column=1, value="Net Debt / LTM EBITDA")
        nd_sheet.cell(row=2, column=2, value=net_debt.get("net_debt_to_ebitda"))
        bridge_rows = [
            [c.get("label"), str(c.get("amount")), "Yes" if c.get("is_subtotal") else "No"]
            for c in net_debt["bridge"]
        ]
        next_row = _write_table(nd_sheet, ["Line Item", "Amount", "Subtotal"], bridge_rows, start_row=4)
        if net_debt.get("reconciliation_note"):
            nd_sheet.cell(row=next_row, column=1, value="Reconciliation note")
            nd_sheet.cell(row=next_row, column=2, value=net_debt["reconciliation_note"])

        if net_debt.get("instruments"):
            debt_sheet = wb.create_sheet("Debt Instruments")
            debt_rows = [
                [
                    i.get("instrument_id"), i.get("facility_type"), i.get("lender"),
                    str(i.get("principal_outstanding")), str(i.get("interest_rate_pct")),
                    i.get("maturity_date"), i.get("source_document"),
                ]
                for i in net_debt["instruments"]
            ]
            _write_table(
                debt_sheet,
                ["ID", "Facility Type", "Lender", "Principal", "Rate %", "Maturity", "Source"],
                debt_rows,
            )

    # DCF
    dcf = _load_json(processed / "dcf_report.json")
    if not dcf or dcf.get("status") != "complete":
        logger.warning(
            "Databook: 'DCF' sheet omitted for deal %s — dcf_report.json not found or "
            "status != 'complete' (%s)",
            deal_id, dcf.get("status") if dcf else "no file",
        )
    else:
        dcf_sheet = wb.create_sheet("DCF")
        assumptions = dcf.get("assumptions") or {}
        headline_rows = [
            ["Discount rate (annual)", assumptions.get("discount_rate_annual")],
            ["Terminal growth rate (annual)", assumptions.get("terminal_growth_rate_annual")],
            ["Sum PV of FCF", str(dcf.get("sum_pv_of_fcf"))],
            ["Terminal value", str(dcf.get("terminal_value"))],
            ["PV of terminal value", str(dcf.get("pv_of_terminal_value"))],
            ["Enterprise value", str(dcf.get("enterprise_value"))],
        ]
        next_row = _write_table(dcf_sheet, ["Assumption / Output", "Value"], headline_rows)
        fcf_rows = [
            [period, str(amount), str(dcf.get("pv_of_fcf", {}).get(period))]
            for period, amount in dcf.get("projected_fcf", {}).items()
        ]
        next_row = _write_table(dcf_sheet, ["Period", "Projected FCF", "PV of FCF"], fcf_rows, start_row=next_row)
        for i, limitation in enumerate(dcf.get("limitations", [])):
            dcf_sheet.cell(row=next_row + i, column=1, value=f"Limitation: {limitation}")

    # Commercial Health
    commercial = _load_json(processed / "commercial_report.json")
    if not commercial or commercial.get("status") == "skipped":
        logger.warning(
            "Databook: 'Commercial Health' sheet omitted for deal %s — commercial_report.json "
            "not found or skipped (%s)",
            deal_id, commercial.get("message") if commercial else "no file",
        )
    else:
        comm_sheet = wb.create_sheet("Commercial Health")
        comm_sheet.cell(row=1, column=1, value=commercial.get("message"))
        comm_sheet.cell(row=2, column=1, value="Revenue volatility (coefficient of variation)")
        comm_sheet.cell(row=2, column=2, value=commercial.get("revenue_volatility"))
        comm_sheet.cell(row=3, column=1, value="Seasonality")
        comm_sheet.cell(row=3, column=2, value=commercial.get("seasonality_note") or "Not detected")

        growth_rows = [list(item) for item in sorted(commercial.get("revenue_growth_yoy_pct", {}).items())]
        next_row = _write_table(comm_sheet, ["Year", "Revenue Growth YoY %"], growth_rows, start_row=5)

        gm = commercial.get("gross_margin_trend_pct", {})
        em = commercial.get("ebitda_margin_trend_pct", {})
        margin_rows = [[period, gm.get(period), em.get(period)] for period in sorted(gm.keys())]
        next_row = _write_table(
            comm_sheet, ["Period", "Gross Margin %", "EBITDA Margin %"], margin_rows, start_row=next_row
        )
        for i, unavailable in enumerate(commercial.get("unavailable_metrics", [])):
            comm_sheet.cell(row=next_row + i, column=1, value=f"Unavailable: {unavailable}")

    # Contract Covenants & Clauses
    contracts = _load_json(processed / "contract_analysis.json")
    if not contracts or contracts.get("status") == "skipped":
        logger.warning(
            "Databook: 'Contracts' sheet omitted for deal %s — contract_analysis.json not "
            "found or skipped (contracts analysis is manually triggered, separate from the "
            "main pipeline — see POST /deals/{id}/contracts/analyze)",
            deal_id,
        )
    else:
        contracts_sheet = wb.create_sheet("Contracts")
        instrument_rows = [
            [
                i.get("instrument_id"), i.get("lender"), i.get("covenants_summary"),
                i.get("change_of_control_clause"), i.get("prepayment_terms"),
                i.get("events_of_default"), "; ".join(i.get("material_obligations", [])),
            ]
            for i in contracts.get("instruments", [])
        ]
        next_row = _write_table(
            contracts_sheet,
            ["Instrument", "Lender", "Covenants", "Change of Control", "Prepayment Terms",
             "Events of Default", "Material Obligations"],
            instrument_rows,
        )
        clause_rows = [
            [c.get("clause_type"), c.get("summary"), c.get("source_document"), c.get("confidence")]
            for c in contracts.get("clauses", [])
        ]
        next_row = _write_table(
            contracts_sheet, ["Clause Type", "Summary", "Source", "Confidence"], clause_rows, start_row=next_row
        )
        for i, warning in enumerate(contracts.get("extraction_warnings", [])):
            contracts_sheet.cell(row=next_row + i, column=1, value=f"Warning: {warning}")

    # Narrative
    narrative = _load_json(processed / "narrative_report.json")
    if not narrative or not narrative.get("sections"):
        logger.warning(
            "Databook: 'Narrative' sheet omitted for deal %s — narrative_report.json not "
            "found or has no sections (narrative_drafter hasn't run)",
            deal_id,
        )
    else:
        narrative_sheet = wb.create_sheet("Narrative")
        narrative_rows = [[s.get("title"), s.get("content")] for s in narrative["sections"]]
        _write_table(narrative_sheet, ["Section", "Content"], narrative_rows)
        narrative_sheet.column_dimensions["B"].width = 100

    # AR/AP Aging
    for fname, title in [("ar_aging.json", "AR Aging"), ("ap_aging.json", "AP Aging")]:
        data = _load_json(processed / fname)
        if not data:
            logger.warning(
                "Databook: '%s' sheet omitted for deal %s — %s not found (aging file not uploaded)",
                title, deal_id, fname,
            )
            continue
        sheet = wb.create_sheet(title)
        summaries = data.get("summaries", [])
        aging_rows = [
            [
                s.get("period"),
                str(s.get("bucket_0_30")),
                str(s.get("bucket_31_60")),
                str(s.get("bucket_61_90")),
                str(s.get("bucket_90_plus")),
                str(s.get("total")),
            ]
            for s in summaries
        ]
        _write_table(
            sheet,
            ["Period", "0-30", "31-60", "61-90", "90+", "Total"],
            aging_rows,
        )

    # Cross-doc tie-outs
    cross = _load_json(processed / "cross_document_validation.json")
    if not cross:
        logger.warning(
            "Databook: 'Tie-outs' sheet omitted for deal %s — cross_document_validation.json "
            "not found (ingestion hasn't run, or no AR/AP aging was uploaded to tie out)",
            deal_id,
        )
    if cross:
        tie_sheet = wb.create_sheet("Tie-outs")
        tie_rows = [
            [
                t.get("name"),
                str(t.get("expected")),
                str(t.get("observed")),
                str(t.get("difference")),
                t.get("variance_pct"),
                t.get("status"),
            ]
            for t in cross.get("tie_outs", [])
        ]
        _write_table(
            tie_sheet,
            ["Tie-out", "Expected (GL)", "Observed (Doc)", "Diff", "Variance %", "Status"],
            tie_rows,
        )

    # IRL
    irl_sheet = wb.create_sheet("IRL")
    irl_rows = _build_irl_rows(deal_id, processed, cross)
    _write_table(
        irl_sheet,
        ["Request", "Severity", "Owner", "Source", "Blocking"],
        irl_rows,
    )

    buf = BytesIO()
    wb.save(buf)
    logger.info("Databook generated for deal %s (%d sheets)", deal_id, len(wb.sheetnames))
    return buf.getvalue()


def _build_irl_rows(deal_id: str, processed: Path, cross: dict | None) -> list[list]:
    rows: list[list] = []

    redflags = _load_json(processed / "redflag_report.json")
    if redflags:
        for flag in redflags.get("flags", []):
            for q in flag.get("diligence_questions", []):
                rows.append([q, flag.get("severity", "Medium"), "Management", "Red Flag", "No"])

    if cross:
        for tie in cross.get("tie_outs", []):
            if tie.get("status") in ("Warn", "Fail"):
                rows.append([
                    f"Reconcile {tie.get('name')} variance of {tie.get('difference')}",
                    "Medium",
                    "Controller",
                    "Cross-doc validation",
                    "Yes",
                ])

    inventory = _load_json(processed / "document_inventory.json")
    if inventory:
        for missing in inventory.get("missing_recommended", []):
            rows.append([
                f"Provide {missing.replace('_', ' ')} document",
                "Medium",
                "Data Room Owner",
                "Document inventory",
                "No",
            ])

    if not rows:
        rows.append(["No open diligence requests at this time.", "Informational", "N/A", "System", "No"])

    return rows
