"""
Golden-path end-to-end test — the full acceptance-criteria loop in one run.

Uploads the multi-document data room fixture (GL + AR/AP aging + management
projections + a credit agreement PDF), runs every default pipeline stage, and
asserts every reporting endpoint returns real, internally-consistent data:
P&L/BS, QoE waterfall, red flags, NWC peg, net debt bridge, DCF, contracts,
narrative, and the Excel databook export.

This is the "single processed deal with multi-doc upload" acceptance scenario
from the mission brief — run with USE_MOCK_LLM=true (no API cost).
"""

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

FIXTURES = Path(__file__).parent.parent / "fixtures"
DATA_ROOM_ZIP = FIXTURES / "data_room.zip"

client = TestClient(app)
from tests.auth_helpers import authenticate as _authenticate  # noqa: E402

_authenticate(client)


@pytest.fixture(scope="module", autouse=True)
def require_fixture():
    if not DATA_ROOM_ZIP.exists():
        pytest.skip(f"{DATA_ROOM_ZIP.name} missing")


def test_golden_path_full_pipeline_and_all_endpoints():
    # 1. Create deal
    resp = client.post("/api/v1/deals", json={
        "company_name": "Golden Path Acme Co", "deal_name": "Golden Path E2E", "currency": "USD",
    })
    assert resp.status_code == 201
    deal_id = resp.json()["deal_id"]

    # 2. Upload the full multi-document data room ZIP
    with open(DATA_ROOM_ZIP, "rb") as f:
        upload_resp = client.post(
            f"/api/v1/deals/{deal_id}/upload",
            files={"files": ("data_room.zip", f, "application/zip")},
        )
    assert upload_resp.status_code == 200
    assert upload_resp.json()["files_received"] >= 5

    # 3. Trigger the full default pipeline (all stages, no explicit list)
    process_resp = client.post(f"/api/v1/deals/{deal_id}/process", json={})
    assert process_resp.status_code == 200
    all_stages = process_resp.json()["stages_queued"]
    assert "narrative_drafter" in all_stages

    for _ in range(240):
        status = client.get(f"/api/v1/deals/{deal_id}/status").json()
        stages = status["stages"]
        if all(stages.get(s) == "complete" for s in all_stages):
            break
        if any(stages.get(s) == "failed" for s in all_stages):
            pytest.fail(f"Pipeline failed at stage(s): {stages}. Error: {status.get('error')}")
        time.sleep(0.5)
    else:
        pytest.fail("Golden path pipeline timed out")

    # 4. Financials — live P&L / BS / CF
    pnl = client.get(f"/api/v1/deals/{deal_id}/financials/pnl?period=annual")
    assert pnl.status_code == 200
    assert len(pnl.json()["periods"]) == 3

    bs = client.get(f"/api/v1/deals/{deal_id}/financials/balance-sheet")
    assert bs.status_code == 200
    assert all(bs.json()["is_balanced"].values())

    cf = client.get(f"/api/v1/deals/{deal_id}/financials/cash-flow")
    assert cf.status_code == 200

    # 5. QoE waterfall + adjustment drill-through
    qoe = client.get(f"/api/v1/deals/{deal_id}/qoe")
    assert qoe.status_code == 200
    qoe_data = qoe.json()
    assert qoe_data["adjustment_count"] > 0
    waterfall_sum = sum(
        float(b["amount"]) for b in qoe_data["waterfall"] if b["type"] in ("base", "addback", "deduction")
    )
    result_amount = next(b["amount"] for b in qoe_data["waterfall"] if b["type"] == "result")
    assert abs(waterfall_sum - float(result_amount)) < 0.01

    first_adj_id = qoe_data["adjustments"][0]["adjustment_id"]
    source = client.get(f"/api/v1/deals/{deal_id}/qoe/adjustments/{first_adj_id}/source")
    assert source.status_code == 200
    assert len(source.json()["gl_lines"]) > 0

    # 6. Red flags with severity + diligence questions
    redflags = client.get(f"/api/v1/deals/{deal_id}/redflags")
    assert redflags.status_code == 200
    assert redflags.json()["summary"]["total"] >= 3

    # 7. Real NWC series + peg
    nwc = client.get(f"/api/v1/deals/{deal_id}/nwc")
    assert nwc.status_code == 200
    nwc_data = nwc.json()
    assert nwc_data["status"] == "complete"
    assert len(nwc_data["data_points"]) == 36
    assert any(p["recommended"] for p in nwc_data["pegs"])

    commercial = client.get(f"/api/v1/deals/{deal_id}/commercial")
    assert commercial.status_code == 200

    # 8. Real net debt bridge (credit agreement PDF was uploaded)
    net_debt = client.get(f"/api/v1/deals/{deal_id}/net-debt")
    assert net_debt.status_code == 200
    nd_data = net_debt.json()
    assert nd_data["status"] == "complete"
    assert len(nd_data["instruments"]) == 1

    # 9. DCF cross-check (management projections were uploaded)
    dcf = client.get(f"/api/v1/deals/{deal_id}/dcf")
    assert dcf.status_code == 200
    assert dcf.json()["status"] == "complete"

    # 10. Contract instruments + clauses
    contracts = client.get(f"/api/v1/deals/{deal_id}/contracts")
    assert contracts.status_code == 200
    contracts_data = contracts.json()
    assert contracts_data["status"] == "complete"
    assert len(contracts_data["clauses"]) > 0
    assert contracts_data["instruments"][0]["change_of_control_clause"]

    # 11. Tie-outs (AR/AP aging vs. GL)
    tieouts = client.get(f"/api/v1/deals/{deal_id}/tie-outs")
    assert tieouts.status_code == 200

    # 12. Documents inventory
    documents = client.get(f"/api/v1/deals/{deal_id}/documents")
    assert documents.status_code == 200
    assert len(documents.json()["documents"]) >= 5

    # 13. Narrative report — every figure quoted must trace to figures_used
    narrative = client.get(f"/api/v1/deals/{deal_id}/narrative")
    assert narrative.status_code == 200
    narrative_data = narrative.json()
    assert len(narrative_data["sections"]) == 5
    exec_summary = next(s for s in narrative_data["sections"] if s["section_id"] == "executive_summary")
    assert narrative_data["figures_used"]["adjusted_ebitda_ltm"] in exec_summary["content"]

    # 14. Excel databook export still works
    databook = client.post(f"/api/v1/deals/{deal_id}/databook/export")
    assert databook.status_code == 200
    assert databook.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert len(databook.content) > 1000
