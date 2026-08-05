"""
Step 7 tests — Contract Analysis (clause extraction + analyze/get API).

All run with USE_MOCK_LLM=true (no API cost).
Key assertions:
  - Heuristic extraction grounds change-of-control / prepayment / events-of-default /
    material obligations in the actual PDF text (not invented)
  - ContractAnalysisReport flattens instrument clause fields into a clause list
  - GET /contracts works after a normal /process run (no explicit /analyze needed)
  - POST /contracts/analyze re-runs extraction and is idempotent
  - No debt agreement uploaded -> "skipped", not fabricated data
"""

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.agents.contract_parser import extract_debt_heuristics
from app.main import app
from app.pipeline.contracts import orchestrator as contract_orch
from app.pipeline.contracts.pdf_extractor import extract_text
from app.schemas.contracts import DebtInstrument

FIXTURES = Path(__file__).parent.parent / "fixtures"
PDF_NAME = "Credit_Agreement_FNB.pdf"
PDF_PATH = FIXTURES / PDF_NAME
DEAL_ID = "test-contracts-001"

client = TestClient(app)
from tests.auth_helpers import authenticate as _authenticate  # noqa: E402

_authenticate(client)


@pytest.fixture(scope="module", autouse=True)
def require_pdf_fixture():
    if not PDF_PATH.exists():
        pytest.skip(f"{PDF_NAME} missing — run: python tests/fixtures/generate_credit_agreement_pdf.py")


@pytest.mark.unit
class TestClauseHeuristics:
    def test_change_of_control_grounded_in_text(self):
        text = extract_text(PDF_PATH)
        result = extract_debt_heuristics(text)
        clause = result["instruments"][0]["change_of_control_clause"]
        assert "Change of Control" in clause
        assert "30 days" in clause

    def test_prepayment_grounded_in_text(self):
        text = extract_text(PDF_PATH)
        result = extract_debt_heuristics(text)
        clause = result["instruments"][0]["prepayment_terms"]
        assert "1.00%" in clause
        assert "prepay" in clause.lower()

    def test_events_of_default_grounded_in_text(self):
        text = extract_text(PDF_PATH)
        result = extract_debt_heuristics(text)
        clause = result["instruments"][0]["events_of_default"]
        assert "Event of Default" in clause

    def test_material_obligations_split_into_list(self):
        text = extract_text(PDF_PATH)
        result = extract_debt_heuristics(text)
        obligations = result["instruments"][0]["material_obligations"]
        assert len(obligations) == 3
        assert any("insurance" in o for o in obligations)
        assert any("audited annual financial statements" in o for o in obligations)
        assert any("material litigation" in o for o in obligations)

    def test_no_clauses_when_text_lacks_them(self):
        result = extract_debt_heuristics("Principal Outstanding: $100.00")
        inst = result["instruments"][0]
        assert "change_of_control_clause" not in inst
        assert "material_obligations" not in inst


@pytest.mark.unit
class TestParseResponseRaisesOnMissingToolCall:
    """A real API response with no tool-use block must raise AgentError — not silently
    return {'instruments': []}, which is indistinguishable from 'this contract genuinely
    has no debt terms'."""

    def test_no_tool_use_block_raises_agent_error(self):
        from app.agents.base import AgentError
        from app.agents.contract_parser import ContractParserAgent

        class _FakeBlock:
            pass  # no .input attribute

        class _FakeResponse:
            content = [_FakeBlock()]

        agent = ContractParserAgent()
        with pytest.raises(AgentError):
            agent._parse_response(_FakeResponse())

    def test_no_content_attribute_raises_agent_error(self):
        from app.agents.base import AgentError
        from app.agents.contract_parser import ContractParserAgent

        agent = ContractParserAgent()
        with pytest.raises(AgentError):
            agent._parse_response(object())


@pytest.mark.unit
class TestBuildClauses:
    def test_flattens_instrument_fields_into_clauses(self):
        inst = DebtInstrument(
            instrument_id="DEBT-X",
            deal_id=DEAL_ID,
            facility_type="term_loan",
            change_of_control_clause="COC text",
            prepayment_terms="Prepay text",
            events_of_default="EoD text",
            covenants_summary="Covenant text",
            material_obligations=["Obligation A", "Obligation B"],
            source_document=PDF_NAME,
            extraction_confidence=0.9,
        )
        clauses = contract_orch._build_clauses([inst])
        types = {c.clause_type for c in clauses}
        assert types == {"change_of_control", "prepayment", "event_of_default", "covenant", "material_obligation"}
        assert sum(1 for c in clauses if c.clause_type == "material_obligation") == 2
        assert all(c.instrument_id == "DEBT-X" for c in clauses)
        assert all(c.source_document == PDF_NAME for c in clauses)


# ─── Full HTTP flow ───────────────────────────────────────────────────────────

def _create_deal(name: str) -> str:
    resp = client.post("/api/v1/deals", json={
        "company_name": name, "deal_name": f"{name} — Contracts Test", "currency": "USD",
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
    for _ in range(120):
        status = client.get(f"/api/v1/deals/{deal_id}/status").json()
        if all(status["stages"].get(s) == "complete" for s in stages):
            return
        if any(status["stages"].get(s) == "failed" for s in stages):
            pytest.fail(f"Pipeline failed: {status.get('error')}")
        time.sleep(0.5)
    pytest.fail("Pipeline timed out")


class TestContractsApi:
    def test_get_contracts_works_after_normal_process_run(self):
        deal_id = _create_deal("Contracts GET Test Co")
        _upload(deal_id, ["sample_gl.csv", PDF_NAME])
        _run_stages(deal_id, ["ingestion"])

        resp = client.get(f"/api/v1/deals/{deal_id}/contracts")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "complete"
        assert len(data["instruments"]) == 1
        # 4 single-value clause fields (change_of_control, prepayment, event_of_default, covenant)
        # + material obligations enumerated from the fixture's 3-item list. The mock heuristic
        # always yields exactly 3 obligations (7 total); a real LLM may reasonably split the
        # list differently (e.g. 4 items), so assert a floor rather than an exact count.
        assert len(data["clauses"]) >= 7
        assert data["instruments"][0]["lender"] == "Horizon Commercial Bank"

    @pytest.mark.flaky(reruns=2, reruns_delay=3)
    def test_analyze_endpoint_reruns_and_is_idempotent(self):
        # Idempotency here means the *structured* extraction is stable across two
        # real calls to the contract-parsing LLM — facility terms, not prose. The
        # free-text narrative fields (covenants_summary, change_of_control_clause,
        # prepayment_terms, events_of_default, material_obligations) can legitimately
        # be phrased differently each call even when the underlying terms are the
        # same, so those are checked for presence only, not byte-for-byte equality.
        deal_id = _create_deal("Contracts Analyze Test Co")
        _upload(deal_id, ["sample_gl.csv", PDF_NAME])
        _run_stages(deal_id, ["ingestion"])

        first = client.post(f"/api/v1/deals/{deal_id}/contracts/analyze")
        assert first.status_code == 200
        second = client.post(f"/api/v1/deals/{deal_id}/contracts/analyze")
        assert second.status_code == 200

        first_instruments = first.json()["instruments"]
        second_instruments = second.json()["instruments"]
        assert len(first_instruments) == len(second_instruments)

        structured_fields = (
            "deal_id", "facility_type", "lender", "principal_outstanding",
            "interest_rate_pct", "maturity_date", "source_document",
        )
        free_text_fields = (
            "covenants_summary", "change_of_control_clause", "prepayment_terms",
            "events_of_default", "material_obligations",
        )
        for first_item, second_item in zip(first_instruments, second_instruments):
            for field in structured_fields:
                assert first_item[field] == second_item[field], (
                    f"structured field {field!r} was not idempotent: "
                    f"{first_item[field]!r} != {second_item[field]!r}"
                )
            for field in free_text_fields:
                assert first_item[field], f"{field!r} was empty on first call"
                assert second_item[field], f"{field!r} was empty on second call"

    def test_skipped_when_no_contract_uploaded(self):
        deal_id = _create_deal("No Contracts Test Co")
        _upload(deal_id, ["sample_gl.csv"])
        _run_stages(deal_id, ["ingestion"])

        resp = client.post(f"/api/v1/deals/{deal_id}/contracts/analyze")
        assert resp.status_code == 200
        assert resp.json()["status"] == "skipped"
        assert resp.json()["instruments"] == []

    def test_contracts_404_before_any_ingestion(self):
        deal_id = _create_deal("Contracts 404 Test Co")
        resp = client.get(f"/api/v1/deals/{deal_id}/contracts")
        assert resp.status_code == 404

    def test_partial_extraction_failure_is_surfaced_not_silently_dropped(self):
        """One good PDF + one corrupt PDF must still report the failure, even though the
        good PDF's instrument makes the overall status 'complete'."""
        corrupt_name = "corrupt_agreement.pdf"
        if not (FIXTURES / corrupt_name).exists():
            pytest.skip(f"{corrupt_name} fixture missing")

        deal_id = _create_deal("Partial Contract Failure Test Co")
        _upload(deal_id, ["sample_gl.csv", PDF_NAME, corrupt_name])
        _run_stages(deal_id, ["ingestion"])

        resp = client.post(f"/api/v1/deals/{deal_id}/contracts/analyze")
        assert resp.status_code == 200
        data = resp.json()

        assert data["status"] == "complete"
        assert len(data["instruments"]) == 1
        assert len(data["extraction_warnings"]) == 1
        assert corrupt_name in data["extraction_warnings"][0]
        assert "could not be processed" in data["message"]
