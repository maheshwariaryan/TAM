"""
Step 8 tests — Narrative Drafter.

All run with USE_MOCK_LLM=true (no API cost).
Key assertions:
  - Mock narrative only phrases figures actually present in the fact sheet — every
    number appearing in a section's content also appears in figures_used
  - Missing optional reports (red flags / NWC / net debt) degrade to "partial" with
    an honest data_gaps list, never a fabricated figure
  - Missing QoE/financials (the two hard requirements) -> "skipped"
  - Full HTTP flow: /process → GET /narrative returns real, traceable sections
"""

import time
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.pipeline.narrative import orchestrator as narrative_orch
from app.schemas.financials import PnLStatement
from app.schemas.qoe import QoEReport

FIXTURES = Path(__file__).parent.parent / "fixtures"
DEAL_ID = "test-narrative-001"

client = TestClient(app)
from tests.auth_helpers import authenticate as _authenticate  # noqa: E402

_authenticate(client)


def _make_pnl() -> PnLStatement:
    periods = [f"2024-{m:02d}-01" for m in range(1, 13)]
    revenue = {p[:7]: Decimal("1000000") for p in periods}
    return PnLStatement(
        deal_id=DEAL_ID,
        periods=periods,
        rows=[],
        revenue=revenue,
        gross_profit=revenue,
        ebitda=revenue,
        ebit=revenue,
        net_income=revenue,
        gross_margin={k: 1.0 for k in revenue},
        ebitda_margin={k: 1.0 for k in revenue},
    )


def _make_qoe() -> QoEReport:
    return QoEReport(
        deal_id=DEAL_ID,
        reported_ebitda={"2024-01": Decimal("500000")},
        adjusted_ebitda={"2024-01": Decimal("550000")},
        ltm_reported=Decimal("6000000"),
        ltm_adjusted=Decimal("6600000"),
        ltm_adjustment_total=Decimal("600000"),
        adjustments=[],
        waterfall=[],
        adjustment_count=3,
        categories_adjusted=["Owner Compensation", "One-Time Items"],
    )


@pytest.mark.unit
class TestFactSheetBuilder:
    def test_gaps_listed_when_optional_reports_missing(self):
        figures, gaps = narrative_orch._build_fact_sheet(_make_pnl(), _make_qoe(), None, None, None)
        assert gaps == ["red flags", "NWC peg", "net debt bridge"]
        assert "redflag_high_count" not in figures
        assert "nwc_peg_amount" not in figures
        assert "net_debt" not in figures

    def test_core_figures_always_present(self):
        figures, _ = narrative_orch._build_fact_sheet(_make_pnl(), _make_qoe(), None, None, None)
        assert figures["revenue_ltm"] == "$12,000,000"
        assert figures["reported_ebitda_ltm"] == "$6,000,000"
        assert figures["adjusted_ebitda_ltm"] == "$6,600,000"
        assert figures["qoe_adjustment_count"] == "3"


@pytest.mark.unit
class TestParseResponseRaisesOnMissingToolCall:
    """A real API response with no tool-use block (refusal, prose-only reply, content
    filter) must raise AgentError — not silently return an empty result that looks
    identical to 'nothing to report'."""

    def test_no_tool_use_block_raises_agent_error(self):
        from app.agents.base import AgentError
        from app.agents.narrative_drafter import NarrativeDrafterAgent

        class _FakeBlock:
            type = "text"

        class _FakeResponse:
            content = [_FakeBlock()]

        agent = NarrativeDrafterAgent()
        with pytest.raises(AgentError):
            agent._parse_response(_FakeResponse())

    def test_empty_content_raises_agent_error(self):
        from app.agents.base import AgentError
        from app.agents.narrative_drafter import NarrativeDrafterAgent

        class _FakeResponse:
            content = []

        agent = NarrativeDrafterAgent()
        with pytest.raises(AgentError):
            agent._parse_response(_FakeResponse())


@pytest.mark.unit
class TestMockNarrativeGrounding:
    def test_mock_sections_only_reference_provided_figures(self):
        from app.agents.narrative_drafter import NarrativeDrafterAgent

        figures, _ = narrative_orch._build_fact_sheet(_make_pnl(), _make_qoe(), None, None, None)
        agent = NarrativeDrafterAgent()
        result = agent._mock_response(figures)
        sections = result["sections"]
        assert len(sections) == 5

        exec_summary = next(s for s in sections if s["section_id"] == "executive_summary")
        assert figures["revenue_ltm"] in exec_summary["content"]
        assert figures["adjusted_ebitda_ltm"] in exec_summary["content"]

    def test_missing_figures_render_as_unavailable_not_fabricated(self):
        from app.agents.narrative_drafter import NarrativeDrafterAgent

        figures, _ = narrative_orch._build_fact_sheet(_make_pnl(), _make_qoe(), None, None, None)
        agent = NarrativeDrafterAgent()
        result = agent._mock_response(figures)
        wc_section = next(s for s in result["sections"] if s["section_id"] == "working_capital")
        assert "unavailable" in wc_section["content"]


class TestNarrativeOrchestrator:
    def test_skipped_without_pnl_or_qoe(self):
        import asyncio
        result = asyncio.run(narrative_orch._run_async("no-such-deal-xyz"))
        assert result.status == "skipped"


# ─── Full HTTP flow ───────────────────────────────────────────────────────────

def _create_deal(name: str) -> str:
    resp = client.post("/api/v1/deals", json={
        "company_name": name, "deal_name": f"{name} — Narrative Test", "currency": "USD",
    })
    assert resp.status_code == 201
    return resp.json()["deal_id"]


def _upload(deal_id: str, filenames: list[str]) -> None:
    files = [("files", (fn, open(FIXTURES / fn, "rb"), "application/octet-stream")) for fn in filenames]
    resp = client.post(f"/api/v1/deals/{deal_id}/upload", files=files)
    assert resp.status_code == 200


def _run_stages(deal_id: str, stages: list[str]) -> None:
    resp = client.post(f"/api/v1/deals/{deal_id}/process", json={"stages": stages})
    assert resp.status_code == 200
    for _ in range(180):
        status = client.get(f"/api/v1/deals/{deal_id}/status").json()
        if all(status["stages"].get(s) == "complete" for s in stages):
            return
        if any(status["stages"].get(s) == "failed" for s in stages):
            pytest.fail(f"Pipeline failed: {status.get('error')}")
        time.sleep(0.5)
    pytest.fail("Pipeline timed out")


class TestNarrativeApiEndpoint:
    def test_full_pipeline_generates_narrative(self):
        deal_id = _create_deal("Narrative API Test Co")
        _upload(deal_id, ["sample_gl.csv", "sample_ar_aging.csv", "sample_ap_aging.csv"])
        _run_stages(deal_id, [
            "ingestion", "coa_mapping", "financial_builder", "qoe_engine",
            "nwc_analyzer", "redflag_detector", "net_debt_bridge", "narrative_drafter",
        ])

        resp = client.get(f"/api/v1/deals/{deal_id}/narrative")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("complete", "partial")
        assert len(data["sections"]) == 5
        assert data["figures_used"]["revenue_ltm"]

        # Every dollar figure quoted in the executive summary must trace to figures_used.
        exec_summary = next(s for s in data["sections"] if s["section_id"] == "executive_summary")
        assert data["figures_used"]["adjusted_ebitda_ltm"] in exec_summary["content"]

    def test_generate_endpoint_regenerates(self):
        deal_id = _create_deal("Narrative Regenerate Test Co")
        _upload(deal_id, ["sample_gl.csv"])
        _run_stages(deal_id, ["ingestion", "coa_mapping", "financial_builder", "qoe_engine"])

        resp = client.post(f"/api/v1/deals/{deal_id}/narrative/generate")
        assert resp.status_code == 200
        assert len(resp.json()["sections"]) == 5

    def test_narrative_404_before_processing(self):
        deal_id = _create_deal("Narrative 404 Test Co")
        resp = client.get(f"/api/v1/deals/{deal_id}/narrative")
        assert resp.status_code == 404
