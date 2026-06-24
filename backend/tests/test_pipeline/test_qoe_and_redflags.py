"""
Step 4 tests — QoE Engine and Red Flag Detector.

All run with USE_MOCK_LLM=true (no API cost).
Key assertions match what a Big 4 TAS reviewer would verify:
  - Every planted anomaly produces a QoE adjustment
  - Adjusted EBITDA > Reported EBITDA (add-backs exceed deductions)
  - Waterfall sum: base + all bar amounts == result
  - Red flags include the expected High and Medium items
  - LTM adjusted EBITDA arithmetic is correct to the cent
"""

import asyncio
from decimal import Decimal
from pathlib import Path

from app.agents.coa_mapper import CoAMapperAgent
from app.pipeline.financial_builder.orchestrator import _apply_classifications
from app.pipeline.ingestion.loader import infer_column_map, load_file
from app.pipeline.ingestion.normalizer import normalise
from app.pipeline.qoe_engine import normalizer as qoe_normalizer
from app.pipeline.qoe_engine import rules as qoe_rules
from app.pipeline.redflag_detector import rules as rf_rules
from app.schemas.qoe import QoEAdjustment

FIXTURE_GL = Path(__file__).parent.parent / "fixtures" / "sample_gl.csv"
DEAL_ID = "test-step4-001"


# ─── Shared fixtures ──────────────────────────────────────────────────────────

def _build_mapped_and_pnl():
    df = load_file(FIXTURE_GL)
    col_map = infer_column_map(df)
    raw = normalise(df, col_map, "sample_gl.csv", DEAL_ID)
    unique_pairs = list({(gl.account_code, gl.account_description) for gl in raw})
    agent = CoAMapperAgent()
    cls_map = asyncio.run(agent.map_accounts(unique_pairs))
    mapped = _apply_classifications(raw, cls_map)

    from app.pipeline.financial_builder import pnl as pnl_builder
    pnl = pnl_builder.build(mapped)
    return mapped, pnl


# ─── QoE Rules tests ──────────────────────────────────────────────────────────

class TestQoERules:
    def setup_method(self):
        self.mapped, self.pnl = _build_mapped_and_pnl()
        self.candidates = qoe_rules.detect_all(self.mapped, DEAL_ID)

    def test_legal_settlement_detected(self):
        legal = [a for a in self.candidates if a.rule_triggered == "LEGAL_SETTLEMENTS"]
        assert len(legal) == 1, f"Expected 1 legal settlement, got {len(legal)}"
        assert legal[0].adjustment_amount == Decimal("285000.00")
        assert legal[0].direction == "add_back"

    def test_ma_costs_detected(self):
        ma = [a for a in self.candidates if a.rule_triggered == "MA_TRANSACTION_COSTS"]
        assert len(ma) == 1
        assert ma[0].adjustment_amount == Decimal("180000.00")

    def test_related_party_detected_all_36_periods(self):
        rp = [a for a in self.candidates if a.rule_triggered == "RELATED_PARTY_CONSULTING"]
        assert len(rp) == 36, f"Expected 36 related-party adjustments, got {len(rp)}"
        total = sum(a.adjustment_amount for a in rp)
        # 36 months × $22,000/mo = $792,000
        assert abs(total - Decimal("792000")) < Decimal("100"), f"RP total ${total} not near $792,000"

    def test_owner_comp_excess_detected_all_36_periods(self):
        comp = [a for a in self.candidates if a.rule_triggered == "OWNER_COMP_EXCESS"]
        assert len(comp) == 36, f"Expected 36 owner comp adjustments, got {len(comp)}"
        # Each should be positive (excess above $65k benchmark)
        for adj in comp:
            assert adj.adjustment_amount > 0
            assert adj.direction == "add_back"

    def test_all_adjustments_have_source_gl_lines(self):
        for adj in self.candidates:
            assert len(adj.source_gl_line_ids) > 0, \
                f"Adjustment '{adj.label}' has no source GL line IDs"

    def test_all_adjustments_are_addbacks(self):
        """For this fixture every rule should produce add-backs, not deductions."""
        for adj in self.candidates:
            assert adj.direction == "add_back", \
                f"Unexpected deduction: {adj.label}"


# ─── QoE Normalizer / Report tests ───────────────────────────────────────────

class TestQoENormalizer:
    def setup_method(self):
        self.mapped, self.pnl = _build_mapped_and_pnl()
        candidates = qoe_rules.detect_all(self.mapped, DEAL_ID)
        # Simulate mock LLM review: accept all
        approved = [a.model_copy(update={"llm_reviewed": True}) for a in candidates]
        self.report = qoe_normalizer.build_report(self.pnl, approved, DEAL_ID)

    def test_adjusted_ebitda_gt_reported_every_period(self):
        for pk in self.report.reported_ebitda:
            assert self.report.adjusted_ebitda[pk] >= self.report.reported_ebitda[pk], \
                f"Adjusted EBITDA < Reported in period {pk}"

    def test_ltm_arithmetic(self):
        """LTM adjusted = LTM reported + sum of LTM add-backs (to the cent)."""
        ltm_periods = sorted(self.report.reported_ebitda.keys())[-12:]
        ltm_set = set(ltm_periods)

        manual_addbacks = sum(
            a.adjustment_amount
            for a in self.report.adjustments
            if a.period.strftime("%Y-%m") in ltm_set and a.direction == "add_back"
        )
        manual_deductions = sum(
            a.adjustment_amount
            for a in self.report.adjustments
            if a.period.strftime("%Y-%m") in ltm_set and a.direction == "deduction"
        )
        expected_adjusted = self.report.ltm_reported + manual_addbacks - manual_deductions
        assert abs(self.report.ltm_adjusted - expected_adjusted) < Decimal("0.01"), \
            f"LTM adjusted EBITDA mismatch: {self.report.ltm_adjusted} vs expected {expected_adjusted}"

    def test_waterfall_base_equals_ltm_reported(self):
        base_items = [w for w in self.report.waterfall if w.type == "base"]
        assert len(base_items) == 1
        assert abs(base_items[0].amount - self.report.ltm_reported) < Decimal("0.01")

    def test_waterfall_result_equals_ltm_adjusted(self):
        result_items = [w for w in self.report.waterfall if w.type == "result"]
        assert len(result_items) == 1
        assert abs(result_items[0].amount - self.report.ltm_adjusted) < Decimal("0.01")

    def test_waterfall_bars_sum_to_adjustment_total(self):
        """base + sum(bars) == result."""
        base = next(w.amount for w in self.report.waterfall if w.type == "base")
        bars = sum(w.amount for w in self.report.waterfall if w.type in ("addback", "deduction"))
        result = next(w.amount for w in self.report.waterfall if w.type == "result")
        assert abs(base + bars - result) < Decimal("0.01"), \
            f"Waterfall doesn't balance: {base} + {bars} ≠ {result}"

    def test_categories_populated(self):
        assert len(self.report.categories_adjusted) > 0
        assert "One-Time / Non-Recurring" in self.report.categories_adjusted
        assert "Owner / Related Party" in self.report.categories_adjusted


# ─── Red Flag Detector tests ──────────────────────────────────────────────────

class TestRedFlagRules:
    def setup_method(self):
        self.mapped, self.pnl = _build_mapped_and_pnl()
        candidates = qoe_rules.detect_all(self.mapped, DEAL_ID)
        approved = [a.model_copy(update={"llm_reviewed": True}) for a in candidates]
        self.qoe = qoe_normalizer.build_report(self.pnl, approved, DEAL_ID)
        self.flags = rf_rules.detect_all(
            deal_id=DEAL_ID,
            pnl=self.pnl,
            mapped_lines=self.mapped,
            qoe=self.qoe,
        )

    def test_flags_present(self):
        assert len(self.flags) > 0, "Expected at least one red flag"

    def test_related_party_flag_is_high(self):
        rp_flags = [f for f in self.flags if f.rule_id == "RELATED_PARTY_MATERIAL"]
        assert len(rp_flags) == 1
        assert rp_flags[0].severity == "High"

    def test_owner_comp_flag_is_medium(self):
        oc_flags = [f for f in self.flags if f.rule_id == "OWNER_COMP_HIGH"]
        assert len(oc_flags) == 1
        assert oc_flags[0].severity == "Medium"

    def test_qoe_informational_flag_present(self):
        info_flags = [f for f in self.flags if f.rule_id == "QOE_ITEMS_PRESENT"]
        assert len(info_flags) == 1
        assert info_flags[0].severity == "Informational"

    def test_flags_sorted_high_first(self):
        order = {"High": 0, "Medium": 1, "Low": 2, "Informational": 3}
        severities = [order[f.severity] for f in self.flags]
        assert severities == sorted(severities), "Flags not sorted by severity"

    def test_all_flags_have_description(self):
        for flag in self.flags:
            assert len(flag.description) > 20, f"Flag '{flag.title}' has thin description"

    def test_high_flags_have_impact_estimates(self):
        high_flags = [f for f in self.flags if f.severity == "High"]
        for flag in high_flags:
            assert flag.financial_impact_low is not None, \
                f"High flag '{flag.title}' missing impact_low"
            assert flag.financial_impact_high is not None, \
                f"High flag '{flag.title}' missing impact_high"
            assert flag.financial_impact_high >= flag.financial_impact_low

    def test_flag_affected_periods_populated(self):
        for flag in self.flags:
            assert len(flag.affected_periods) > 0, \
                f"Flag '{flag.title}' has no affected_periods"


# ─── Agent mock tests ─────────────────────────────────────────────────────────

class TestAgentMocks:
    def test_qoe_reviewer_accepts_all_in_mock(self):
        from datetime import date

        from app.agents.qoe_reviewer import QoEReviewerAgent

        candidates = [
            QoEAdjustment(
                adjustment_id="test-001",
                deal_id=DEAL_ID,
                period=date(2024, 1, 1),
                label="Test Adjustment",
                category="One-Time",
                direction="add_back",
                reported_amount=Decimal("100000"),
                adjustment_amount=Decimal("100000"),
                normalized_amount=Decimal("0"),
                detection_method="rule",
                rule_triggered="LEGAL_SETTLEMENTS",
            )
        ]
        agent = QoEReviewerAgent()
        result = asyncio.run(agent.review(candidates))
        assert len(result) == 1
        assert result[0].llm_reviewed is True

    def test_redflag_analyst_mock_returns_questions(self):
        from app.agents.redflag_analyst import RedFlagAnalystAgent
        from app.schemas.redflags import RedFlag

        flag = RedFlag(
            flag_id="flag-001",
            deal_id=DEAL_ID,
            severity="High",
            category="Revenue Quality",
            title="Test Flag",
            description="A test flag for mock enrichment.",
            source="rule_engine",
            rule_id="TEST",
            affected_periods=["2024-01"],
        )
        agent = RedFlagAnalystAgent()
        result = asyncio.run(agent.enrich([flag]))
        assert len(result) == 1
        assert len(result[0].diligence_questions) == 3
        assert result[0].llm_context is not None


# ─── Red Flag rules with Balance Sheet + Cash Flow ────────────────────────────

class TestRedFlagRulesWithBSCF:
    """
    Verify detect_all() accepts and uses balance_sheet and cash_flow arguments.
    With our synthetic fixture the BS/CF-dependent rules don't breach thresholds
    (AR days ~10d, deferred revenue growing, cash conversion healthy), but the
    function must run without error, return a valid sorted list, and include all
    the base flags that fire without BS/CF.
    """

    @classmethod
    def setup_class(cls):
        from app.pipeline.financial_builder import balance_sheet as bs_builder
        from app.pipeline.financial_builder import cash_flow as cf_builder

        mapped, pnl = _build_mapped_and_pnl()
        candidates = qoe_rules.detect_all(mapped, DEAL_ID)
        approved = [a.model_copy(update={"llm_reviewed": True}) for a in candidates]
        qoe = qoe_normalizer.build_report(pnl, approved, DEAL_ID)

        bs = bs_builder.build(mapped)
        cf = cf_builder.build(mapped, pnl, bs)

        cls.flags_base = rf_rules.detect_all(
            deal_id=DEAL_ID, pnl=pnl, mapped_lines=mapped, qoe=qoe,
        )
        cls.flags_full = rf_rules.detect_all(
            deal_id=DEAL_ID, pnl=pnl, mapped_lines=mapped, qoe=qoe,
            balance_sheet=bs, cash_flow=cf,
        )

    def test_runs_without_error(self):
        assert isinstance(self.flags_full, list)

    def test_flags_still_sorted_high_first(self):
        order = {"High": 0, "Medium": 1, "Low": 2, "Informational": 3}
        severities = [order[f.severity] for f in self.flags_full]
        assert severities == sorted(severities), "Flags not sorted by severity when BS/CF passed"

    def test_base_flags_all_present(self):
        """Every flag that fired without BS/CF must still be present."""
        base_rule_ids = {f.rule_id for f in self.flags_base}
        full_rule_ids = {f.rule_id for f in self.flags_full}
        assert base_rule_ids.issubset(full_rule_ids), (
            f"Rules missing after passing BS/CF: {base_rule_ids - full_rule_ids}"
        )

    def test_count_at_least_as_large(self):
        """BS/CF can only add flags, never remove them."""
        assert len(self.flags_full) >= len(self.flags_base)

    def test_all_flags_valid_structure(self):
        for f in self.flags_full:
            assert f.rule_id is not None
            assert f.severity in {"High", "Medium", "Low", "Informational"}
            assert len(f.affected_periods) > 0
            assert len(f.description) > 10


# ─── Orchestrator integration tests ───────────────────────────────────────────

_ORCH_DEAL_ID = "test-step4-orch-001"


def _setup_orch_pipeline() -> None:
    """
    Write sample_gl.csv to the uploads folder and run all four pipeline stages
    to disk: ingestion → financial_builder → qoe_engine → redflag_detector.
    """
    from app.config import settings
    from app.pipeline.financial_builder import orchestrator as fb_orch
    from app.pipeline.ingestion import orchestrator as ing_orch
    from app.pipeline.qoe_engine import orchestrator as qoe_orch
    from app.pipeline.redflag_detector import orchestrator as rf_orch

    upload_dir = settings.upload_dir / _ORCH_DEAL_ID
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / "sample_gl.csv"
    dest.write_bytes(FIXTURE_GL.read_bytes())

    ing_orch.run(_ORCH_DEAL_ID)
    fb_orch.run(_ORCH_DEAL_ID)
    qoe_orch.run(_ORCH_DEAL_ID)
    rf_orch.run(_ORCH_DEAL_ID)


class TestQoEOrchestrator:
    """
    End-to-end disk persistence tests for the QoE and red-flag orchestrators.
    Runs the full pipeline once per class via setup_class.
    """

    @classmethod
    def setup_class(cls):
        _setup_orch_pipeline()

        from app.config import settings
        from app.pipeline.qoe_engine.orchestrator import load_qoe_report
        from app.pipeline.redflag_detector.orchestrator import load_redflag_report

        cls.processed_dir = settings.processed_dir / _ORCH_DEAL_ID
        cls.qoe_report = load_qoe_report(_ORCH_DEAL_ID)
        cls.rf_report = load_redflag_report(_ORCH_DEAL_ID)

    # ── QoE persistence ────────────────────────────────────────────────────────

    def test_qoe_report_json_on_disk(self):
        assert (self.processed_dir / "qoe_report.json").exists()

    def test_qoe_adjusted_gt_reported(self):
        assert self.qoe_report.ltm_adjusted > self.qoe_report.ltm_reported, (
            "Adjusted LTM EBITDA must be greater than reported (all planted items are add-backs)"
        )

    def test_qoe_at_least_4_adjustments(self):
        """All four planted anomaly types must generate adjustments."""
        rule_ids = {a.rule_triggered for a in self.qoe_report.adjustments}
        expected = {
            "LEGAL_SETTLEMENTS",
            "MA_TRANSACTION_COSTS",
            "RELATED_PARTY_CONSULTING",
            "OWNER_COMP_EXCESS",
        }
        assert expected.issubset(rule_ids), (
            f"Missing adjustment rules: {expected - rule_ids}"
        )

    def test_qoe_waterfall_balances(self):
        """Waterfall: base + bars == result (to the cent)."""
        base = next(w.amount for w in self.qoe_report.waterfall if w.type == "base")
        bars = sum(
            w.amount for w in self.qoe_report.waterfall if w.type in ("addback", "deduction")
        )
        result = next(w.amount for w in self.qoe_report.waterfall if w.type == "result")
        assert abs(base + bars - result) < Decimal("0.01"), (
            f"Waterfall doesn't balance: {base} + {bars} ≠ {result}"
        )

    def test_qoe_ltm_arithmetic(self):
        """LTM adjusted == LTM reported + net add-backs (to the cent)."""
        ltm_periods = set(sorted(self.qoe_report.reported_ebitda.keys())[-12:])
        net = sum(
            a.adjustment_amount * (1 if a.direction == "add_back" else -1)
            for a in self.qoe_report.adjustments
            if a.period.strftime("%Y-%m") in ltm_periods
        )
        expected = self.qoe_report.ltm_reported + net
        assert abs(self.qoe_report.ltm_adjusted - expected) < Decimal("0.01"), (
            f"LTM adjusted {self.qoe_report.ltm_adjusted} ≠ expected {expected}"
        )

    # ── Red Flag persistence ────────────────────────────────────────────────────

    def test_redflag_report_json_on_disk(self):
        assert (self.processed_dir / "redflag_report.json").exists()

    def test_at_least_3_flags(self):
        assert len(self.rf_report.flags) >= 3, (
            f"Expected ≥3 flags, got {len(self.rf_report.flags)}"
        )

    def test_has_high_severity_flag(self):
        high = [f for f in self.rf_report.flags if f.severity == "High"]
        assert len(high) >= 1, "Expected at least one High severity flag"

    def test_related_party_flag_present(self):
        rp = [f for f in self.rf_report.flags if f.rule_id == "RELATED_PARTY_MATERIAL"]
        assert len(rp) == 1
        assert rp[0].severity == "High"

    def test_summary_counts_match_flags(self):
        s = self.rf_report.summary
        assert s.high == sum(1 for f in self.rf_report.flags if f.severity == "High")
        assert s.medium == sum(1 for f in self.rf_report.flags if f.severity == "Medium")
        assert s.total == len(self.rf_report.flags)

    def test_high_medium_flags_enriched_by_llm(self):
        """Mock LLM must have set diligence_questions on all High/Medium flags."""
        for f in self.rf_report.flags:
            if f.severity in ("High", "Medium"):
                assert len(f.diligence_questions) >= 3, (
                    f"Flag '{f.title}' ({f.severity}) missing diligence questions"
                )
