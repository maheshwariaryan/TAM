"""PDF debt extraction — proves terms are grounded in document text."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.agents.contract_parser import extract_debt_heuristics, parse_debt_from_text
from app.pipeline.contracts.pdf_extractor import extract_text
from app.pipeline.ingestion import orchestrator as orch
from app.storage import file_store

FIXTURES = Path(__file__).parent.parent / "fixtures"
PDF_NAME = "Credit_Agreement_FNB.pdf"
PDF_PATH = FIXTURES / PDF_NAME

# Canonical terms written into the fixture PDF by generate_credit_agreement_pdf.py
EXPECTED_LENDER = "Horizon Commercial Bank"
EXPECTED_PRINCIPAL = Decimal("7500000.00")
EXPECTED_RATE = Decimal("7.85")
EXPECTED_MATURITY = date(2029, 12, 15)

# Values previously invented by the filename-based mock — must NOT appear.
LEGACY_MOCK_LENDER = "First National Bank"
LEGACY_MOCK_PRINCIPAL = Decimal("4200000.00")


@pytest.fixture(scope="module", autouse=True)
def require_pdf_fixture():
    if not PDF_PATH.exists():
        pytest.skip(
            f"{PDF_NAME} missing — run: python tests/fixtures/generate_credit_agreement_pdf.py"
        )


@pytest.mark.unit
class TestExtractDebtHeuristics:
    def test_extracts_terms_from_pdf_text(self):
        text = extract_text(PDF_PATH)
        result = extract_debt_heuristics(text)

        assert len(result["instruments"]) == 1
        inst = result["instruments"][0]
        assert inst["facility_type"] == "term_loan"
        assert inst["lender"] == EXPECTED_LENDER
        assert Decimal(inst["principal_outstanding"]) == EXPECTED_PRINCIPAL
        assert Decimal(inst["interest_rate_pct"]) == EXPECTED_RATE
        assert inst["maturity_date"] == EXPECTED_MATURITY.isoformat()
        assert "3.25x" in inst["covenants_summary"]
        assert "2.00x" in inst["covenants_summary"]
        assert result["extraction_confidence"] >= 0.8

    def test_empty_text_returns_no_instruments(self):
        result = extract_debt_heuristics("")
        assert result["instruments"] == []
        assert result["extraction_confidence"] == 0.0

    def test_does_not_invent_legacy_mock_terms(self):
        text = extract_text(PDF_PATH)
        result = extract_debt_heuristics(text)
        inst = result["instruments"][0]
        assert inst["lender"] != LEGACY_MOCK_LENDER
        assert Decimal(inst["principal_outstanding"]) != LEGACY_MOCK_PRINCIPAL


class TestParseDebtFromText:
    @pytest.mark.asyncio
    async def test_mock_mode_grounds_in_text(self):
        text = extract_text(PDF_PATH)
        instruments = await parse_debt_from_text("deal-pdf-unit", text, PDF_NAME)

        assert len(instruments) == 1
        inst = instruments[0]
        assert inst["lender"] == EXPECTED_LENDER
        assert inst["principal_outstanding"] == EXPECTED_PRINCIPAL
        assert inst["interest_rate_pct"] == EXPECTED_RATE
        assert inst["maturity_date"] == EXPECTED_MATURITY
        assert inst["source_document"] == PDF_NAME
        assert inst["extraction_confidence"] >= 0.8
        assert "3.25x" in (inst["covenants_summary"] or "")


class TestPdfDebtIngestion:
    def test_gl_plus_pdf_persists_debt_instruments(self):
        deal_id = "pdf-debt-ingest"
        gl_src = FIXTURES / "sample_gl.csv"
        file_store.save_upload(deal_id, "sample_gl.csv", gl_src.read_bytes())
        file_store.save_upload(deal_id, PDF_NAME, PDF_PATH.read_bytes())

        result = orch.run(deal_id)

        assert result.debt_schedule is not None
        assert len(result.debt_schedule.instruments) == 1
        inst = result.debt_schedule.instruments[0]
        assert inst.lender == EXPECTED_LENDER
        assert inst.principal_outstanding == EXPECTED_PRINCIPAL
        assert inst.interest_rate_pct == EXPECTED_RATE
        assert inst.maturity_date == EXPECTED_MATURITY
        assert inst.source_document == PDF_NAME
        assert "3.25x" in (inst.covenants_summary or "")

        # Persisted artifact must match — this is what downstream stages read.
        from app.storage.json_io import read_json_encrypted

        debt_path = file_store.get_processed_dir(deal_id) / "debt_instruments.json"
        assert debt_path.exists()
        raw = json.dumps(read_json_encrypted(debt_path))
        assert EXPECTED_LENDER in raw
        assert "7500000" in raw
        assert LEGACY_MOCK_LENDER not in raw
