"""
Unit tests for the GL ingestion pipeline: loader, normalizer, validator.

Tests use the pre-generated sample_gl.csv fixture and synthetic in-memory DataFrames.
No database, no network, no LLM calls.
"""

from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from app.pipeline.ingestion.loader import LoaderError, infer_column_map, load_file
from app.pipeline.ingestion.normalizer import normalise
from app.pipeline.ingestion.validator import validate

FIXTURE_GL = Path(__file__).parent.parent / "fixtures" / "sample_gl.csv"
DEAL_ID = "test-deal-001"


# ─── Loader tests ─────────────────────────────────────────────────────────────

class TestLoader:
    def test_loads_fixture_csv(self):
        df = load_file(FIXTURE_GL)
        assert len(df) == 1514
        assert "account_code" in df.columns
        assert "debit" in df.columns
        assert "credit" in df.columns

    def test_raises_on_missing_file(self):
        with pytest.raises(LoaderError, match="not found"):
            load_file("nonexistent_file.csv")

    def test_raises_on_unsupported_extension(self, tmp_path):
        bad = tmp_path / "data.txt"
        bad.write_text("hello")
        with pytest.raises(LoaderError, match="Unsupported file type"):
            load_file(bad)

    def test_raises_on_empty_csv(self, tmp_path):
        empty = tmp_path / "empty.csv"
        empty.write_text("account_code,debit,credit\n")
        with pytest.raises(LoaderError, match="no data rows"):
            load_file(empty)

    def test_column_inference_standard(self):
        df = pd.DataFrame(columns=["period", "account_code", "account_description", "debit", "credit"])
        mapping = infer_column_map(df)
        assert mapping["period"] == "period"
        assert mapping["account_code"] == "account_code"
        assert mapping["debit"] == "debit"
        assert mapping["credit"] == "credit"

    def test_column_inference_alternative_names(self):
        df = pd.DataFrame(columns=["GL Date", "Acct Code", "Description", "Dr Amount", "Cr Amount"])
        mapping = infer_column_map(df)
        assert mapping["GL Date"] == "period"
        assert mapping["Acct Code"] == "account_code"
        assert mapping["Dr Amount"] == "debit"
        assert mapping["Cr Amount"] == "credit"

    def test_column_inference_raises_without_date(self):
        df = pd.DataFrame(columns=["account_code", "debit", "credit"])
        with pytest.raises(LoaderError, match="date/period column"):
            infer_column_map(df)

    def test_column_inference_raises_without_amount(self):
        df = pd.DataFrame(columns=["period", "account_code", "description"])
        with pytest.raises(LoaderError, match="debit, credit, or amount column"):
            infer_column_map(df)


# ─── Normalizer tests ─────────────────────────────────────────────────────────

class TestNormalizer:
    def _make_df(self, rows: list[dict]) -> pd.DataFrame:
        return pd.DataFrame(rows)

    def _std_map(self) -> dict[str, str]:
        return {
            "period": "period",
            "account_code": "account_code",
            "account_description": "account_description",
            "debit": "debit",
            "credit": "credit",
        }

    def test_normalises_fixture(self):
        df = load_file(FIXTURE_GL)
        mapping = infer_column_map(df)
        lines = normalise(df, mapping, "sample_gl.csv", DEAL_ID)
        assert len(lines) == 1514

    def test_debit_credit_to_signed_amount(self):
        df = self._make_df([
            {"period": "2024-01-01", "account_code": "4001", "account_description": "Revenue",
             "debit": "0", "credit": "100000"},
            {"period": "2024-01-01", "account_code": "5001", "account_description": "COGS",
             "debit": "80000", "credit": "0"},
        ])
        lines = normalise(df, self._std_map(), "test.csv", DEAL_ID)
        assert len(lines) == 2
        revenue = next(gl for gl in lines if gl.account_code == "4001")
        cogs = next(gl for gl in lines if gl.account_code == "5001")
        assert revenue.amount == Decimal("-100000")   # credit → negative
        assert cogs.amount == Decimal("80000")         # debit → positive

    def test_period_coerced_to_first_of_month(self):
        df = self._make_df([
            {"period": "2024-01-31", "account_code": "4001", "account_description": "Rev",
             "debit": "0", "credit": "50000"},
        ])
        lines = normalise(df, self._std_map(), "test.csv", DEAL_ID)
        assert lines[0].period.day == 1
        assert lines[0].period.month == 1

    def test_handles_us_date_format(self):
        df = self._make_df([
            {"period": "01/31/2024", "account_code": "4001", "account_description": "Rev",
             "debit": "0", "credit": "50000"},
        ])
        lines = normalise(df, self._std_map(), "test.csv", DEAL_ID)
        assert lines[0].period.year == 2024
        assert lines[0].period.month == 1

    def test_handles_comma_separated_amounts(self):
        df = self._make_df([
            {"period": "2024-01-01", "account_code": "5001", "account_description": "COGS",
             "debit": "1,234,567.89", "credit": "0"},
        ])
        lines = normalise(df, self._std_map(), "test.csv", DEAL_ID)
        assert lines[0].amount == Decimal("1234567.89")

    def test_handles_accounting_parentheses(self):
        """Accounting convention: (123,456) means negative."""
        df = pd.DataFrame([
            {"period": "2024-01-01", "account_code": "4001", "account_description": "Rev",
             "amount": "(100000)"},
        ])
        mapping = {"period": "period", "account_code": "account_code",
                   "account_description": "account_description", "amount": "amount"}
        lines = normalise(df, mapping, "test.csv", DEAL_ID)
        assert lines[0].amount == Decimal("-100000")

    def test_skips_blank_rows(self):
        df = self._make_df([
            {"period": "2024-01-01", "account_code": "4001", "account_description": "Rev",
             "debit": "0", "credit": "50000"},
            {"period": "", "account_code": "", "account_description": "", "debit": "", "credit": ""},
            {"period": "2024-01-01", "account_code": "5001", "account_description": "COGS",
             "debit": "40000", "credit": "0"},
        ])
        lines = normalise(df, self._std_map(), "test.csv", DEAL_ID)
        assert len(lines) == 2

    def test_source_row_is_accurate(self):
        """source_row must point to the correct line in the original file (1-indexed + header)."""
        df = self._make_df([
            {"period": "2024-01-01", "account_code": "4001", "account_description": "Rev",
             "debit": "0", "credit": "50000"},
        ])
        lines = normalise(df, self._std_map(), "test.csv", DEAL_ID)
        assert lines[0].source_row == 2  # row 1 = header, row 2 = first data row


# ─── Validator tests ──────────────────────────────────────────────────────────

class TestValidator:
    def _make_lines(self, entries: list[tuple]) -> list:
        """entries: list of (account_code, amount_decimal) tuples."""
        from datetime import date

        from app.schemas.gl import RawGLLine
        return [
            RawGLLine(
                line_id=f"TEST-{i:03d}",
                deal_id=DEAL_ID,
                period=date(2024, 1, 1),
                account_code=code,
                account_description="Test",
                amount=Decimal(str(amount)),
                source_file="test.csv",
                source_row=i + 2,
            )
            for i, (code, amount) in enumerate(entries)
        ]

    def test_fixture_passes_validation(self):
        df = load_file(FIXTURE_GL)
        mapping = infer_column_map(df)
        lines = normalise(df, mapping, "sample_gl.csv", DEAL_ID)
        report = validate(lines, DEAL_ID)
        # Fixture is P&L only → balanced per overall sum check
        assert report.periods_checked == 36
        assert report.total_debits > 0
        assert report.total_credits > 0

    def test_balanced_gl_passes(self):
        lines = self._make_lines([
            ("4001", Decimal("-100000")),  # Revenue credit
            ("5001", Decimal("80000")),    # COGS debit
            ("3002", Decimal("20000")),    # Retained earnings debit
        ])
        report = validate(lines, DEAL_ID)
        assert report.difference == Decimal("0")
        assert report.is_balanced is True

    def test_unbalanced_gl_detected(self):
        lines = self._make_lines([
            ("4001", Decimal("-100000")),
            ("5001", Decimal("50000")),  # Missing $50,000 to balance
        ])
        report = validate(lines, DEAL_ID)
        assert report.difference == Decimal("50000")
        assert report.is_balanced is False

    def test_pl_only_export_flag(self):
        df = load_file(FIXTURE_GL)
        mapping = infer_column_map(df)
        lines = normalise(df, mapping, "sample_gl.csv", DEAL_ID)
        report = validate(lines, DEAL_ID)
        # Fixture now includes BalanceSheet rows so it is a mixed export, not P&L-only
        assert report.is_pl_only_export is False
        assert report.is_mixed_export is True

    def test_full_tb_not_pl_only(self):
        lines = self._make_lines([
            ("1001", Decimal("50000")),
            ("2001", Decimal("-80000")),
            ("3002", Decimal("-90000")),
        ])
        report = validate(lines, DEAL_ID)
        assert report.is_pl_only_export is False

    def test_warns_on_insufficient_periods(self):
        lines = self._make_lines([("4001", Decimal("-10000"))])
        report = validate(lines, DEAL_ID)
        assert any("minimum" in w.lower() or "only" in w.lower() for w in report.warnings)

    def test_warns_on_no_revenue(self):
        lines = self._make_lines([("5001", Decimal("10000")), ("2001", Decimal("-10000"))])
        report = validate(lines, DEAL_ID)
        assert any("revenue" in w.lower() for w in report.warnings)

    def test_36_periods_no_period_warning(self):
        from datetime import date

        from app.schemas.gl import RawGLLine
        lines = []
        for i in range(36):
            yr = 2022 + i // 12
            mo = i % 12 + 1
            lines.append(RawGLLine(
                line_id=f"T-{i:03d}",
                deal_id=DEAL_ID,
                period=date(yr, mo, 1),
                account_code="4001",
                account_description="Revenue",
                amount=Decimal("-100000"),
                source_file="test.csv",
                source_row=i + 2,
            ))
        report = validate(lines, DEAL_ID)
        assert report.periods_checked == 36
        assert not any("minimum" in w.lower() for w in report.warnings)


# ─── End-to-end pipeline test ─────────────────────────────────────────────────

class TestIngestionE2E:
    def test_fixture_end_to_end(self):
        """Load → normalise → validate the real fixture file."""
        df = load_file(FIXTURE_GL)
        mapping = infer_column_map(df)
        lines = normalise(df, mapping, "sample_gl.csv", DEAL_ID)
        report = validate(lines, DEAL_ID)

        # 1514 rows: 902 P&L + 612 BalanceSheet (17 accounts × 36 periods)
        assert len(lines) == 1514

        # 36 months of data
        assert report.periods_checked == 36

        # All planted anomalies are present in the normalised lines
        anomaly_lines = [gl for gl in lines if gl.note and gl.note.startswith("ONE_TIME")]
        assert len(anomaly_lines) == 2, f"Expected 2 one-time anomalies, got {len(anomaly_lines)}"

        related_party = [gl for gl in lines if gl.note and "RELATED_PARTY" in gl.note]
        assert len(related_party) == 36, f"Expected 36 related-party rows, got {len(related_party)}"

        # Legal settlement is in February 2023
        from datetime import date
        settlement = next((gl for gl in anomaly_lines if gl.account_code == "6099"), None)
        assert settlement is not None
        assert settlement.period == date(2023, 2, 1)
        assert settlement.amount == Decimal("285000")

        # M&A fees in June 2024 (month_idx 29: 2022 + 29//12=2024, mo=29%12+1=6)
        ma_fee = next((gl for gl in anomaly_lines if gl.account_code == "6098"), None)
        assert ma_fee is not None
        assert ma_fee.period == date(2024, 6, 1)
        assert ma_fee.amount == Decimal("180000")


class TestExcelParity:
    FIXTURE_XLSX = Path(__file__).parent.parent / "fixtures" / "ABC_Subsidiary.xlsx"

    def test_excel_matches_csv_row_count(self):
        if not self.FIXTURE_XLSX.exists():
            pytest.skip("ABC_Subsidiary.xlsx fixture not present")
        df_csv = load_file(FIXTURE_GL)
        df_xlsx = load_file(self.FIXTURE_XLSX)
        assert len(df_csv) == len(df_xlsx)

    def test_excel_normalises_identically_to_csv(self):
        if not self.FIXTURE_XLSX.exists():
            pytest.skip("ABC_Subsidiary.xlsx fixture not present")
        csv_lines = normalise(
            load_file(FIXTURE_GL), infer_column_map(load_file(FIXTURE_GL)),
            "sample_gl.csv", DEAL_ID,
        )
        xlsx_lines = normalise(
            load_file(self.FIXTURE_XLSX), infer_column_map(load_file(self.FIXTURE_XLSX)),
            "ABC_Subsidiary.xlsx", DEAL_ID,
        )
        csv_tuples = sorted((line.account_code, line.period, line.amount) for line in csv_lines)
        xlsx_tuples = sorted((line.account_code, line.period, line.amount) for line in xlsx_lines)
        assert csv_tuples == xlsx_tuples


class TestOrchestratorFailure:
    def test_unbalanced_full_tb_raises(self, tmp_path, monkeypatch):
        from app.config import settings
        from app.pipeline.ingestion import orchestrator as orch
        from app.pipeline.ingestion.orchestrator import IngestionError

        deal_id = "test-unbalanced-deal"
        upload_dir = settings.upload_dir / deal_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        fixture = Path(__file__).parent.parent / "fixtures" / "unbalanced_trial_balance.csv"
        dest = upload_dir / "unbalanced_trial_balance.csv"
        dest.write_bytes(fixture.read_bytes())

        with pytest.raises(IngestionError, match="Trial balance does not balance"):
            orch.run(deal_id)
