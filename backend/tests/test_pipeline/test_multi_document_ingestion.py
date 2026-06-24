"""Multi-document ingestion pipeline tests."""

from decimal import Decimal
from pathlib import Path

import pytest

from app.config import settings
from app.pipeline.ingestion import orchestrator as orch
from app.pipeline.ingestion.aging_loader import infer_aging_column_map
from app.pipeline.ingestion.aging_normalizer import normalise_aging
from app.pipeline.ingestion.document_registry import classify_by_filename
from app.pipeline.ingestion.loader import load_file
from app.pipeline.ingestion.projections_parser import parse_projections
from app.schemas.documents import DocumentType

FIXTURES = Path(__file__).parent.parent / "fixtures"
DEAL_ID = "multi-doc-test"


def _setup_deal_uploads(deal_id: str, filenames: list[str]) -> None:
    upload_dir = settings.upload_dir / deal_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    for name in filenames:
        src = FIXTURES / name
        (upload_dir / name).write_bytes(src.read_bytes())


class TestDocumentClassification:
    def test_classify_ar_aging(self):
        doc_type, conf = classify_by_filename("AR_Aging_Dec24.xlsx")
        assert doc_type == DocumentType.AR_AGING
        assert conf >= 0.8

    def test_classify_projections(self):
        doc_type, _ = classify_by_filename("Management_Forecast_2025.xlsx")
        assert doc_type == DocumentType.MANAGEMENT_PROJECTIONS

    def test_classify_debt_pdf(self):
        doc_type, _ = classify_by_filename("Credit_Agreement_FNB.pdf")
        assert doc_type == DocumentType.DEBT_AGREEMENT


class TestAgingParser:
    def test_parse_ar_aging(self):
        path = FIXTURES / "sample_ar_aging.csv"
        df = load_file(path)
        col_map = infer_aging_column_map(df, "ar_aging")
        summaries = normalise_aging(df, col_map, path.name, DEAL_ID, "ar_aging")
        assert len(summaries) == 1
        assert summaries[0].total == Decimal("262000")
        assert summaries[0].bucket_0_30 == Decimal("180000")


class TestProjectionsParser:
    def test_parse_projections(self):
        path = FIXTURES / "sample_projections.csv"
        lines = parse_projections(path, DEAL_ID)
        assert len(lines) == 3
        assert lines[0].revenue == Decimal("1100000")
        assert lines[0].ebitda == Decimal("100000")


class TestMultiDocumentOrchestrator:
    def test_full_data_room_ingestion(self):
        deal_id = "multi-doc-full"
        _setup_deal_uploads(deal_id, [
            "sample_gl.csv",
            "sample_ar_aging.csv",
            "sample_ap_aging.csv",
            "sample_projections.csv",
        ])
        result = orch.run(deal_id)
        assert len(result.gl_lines) == 1514
        assert result.ar_aging is not None
        assert result.ap_aging is not None
        assert result.projections is not None
        assert result.cross_validation is not None
        assert len(result.inventory.documents) == 4

    def test_gl_only_still_works(self):
        deal_id = "multi-doc-gl-only"
        _setup_deal_uploads(deal_id, ["sample_gl.csv"])
        result = orch.run(deal_id)
        assert len(result.gl_lines) == 1514
        assert result.ar_aging is None
        assert any("ar_aging" in w for w in result.warnings)

    def test_no_gl_fails(self):
        deal_id = "multi-doc-no-gl"
        _setup_deal_uploads(deal_id, ["sample_ar_aging.csv"])
        from app.pipeline.ingestion.orchestrator import IngestionError
        with pytest.raises(IngestionError, match="No GL lines"):
            orch.run(deal_id)
