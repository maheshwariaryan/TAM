"""
General Ledger schemas — the core data unit flowing through every pipeline stage.

RawGLLine: post-normalization, pre-CoA-mapping. Preserves original account codes.
MappedGLLine: post-CoA-mapping. Adds standard_category and financial_statement flags.

Every line carries source_file + source_row so any figure can be traced back to
the exact row in the client's original file — the audit trail requirement.
"""

from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ChartOfAccountsCategory(StrEnum):
    # Revenue
    REVENUE = "Revenue"
    OTHER_INCOME = "Other Income"

    # Cost of Goods Sold
    COST_OF_GOODS_SOLD = "Cost of Goods Sold"
    DIRECT_LABOUR = "Direct Labour"
    MANUFACTURING_OVERHEAD = "Manufacturing Overhead"
    FREIGHT_IN = "Freight In"

    # Operating Expenses — SG&A
    MANAGEMENT_COMPENSATION = "Management Compensation"
    SALARIES_WAGES = "Salaries & Wages"
    RENT_OCCUPANCY = "Rent & Occupancy"
    UTILITIES = "Utilities"
    INSURANCE = "Insurance"
    MARKETING_ADVERTISING = "Marketing & Advertising"
    PROFESSIONAL_FEES = "Professional Fees"
    IT_SOFTWARE = "IT & Software"
    TRAVEL_ENTERTAINMENT = "Travel & Entertainment"
    OFFICE_EXPENSES = "Office Expenses"
    TELECOMMUNICATIONS = "Telecommunications"

    # Non-recurring / Below-the-line
    LEGAL_SETTLEMENTS = "Legal Settlements"
    MA_TRANSACTION_COSTS = "M&A Transaction Costs"
    RESTRUCTURING = "Restructuring Charges"
    RELATED_PARTY_CONSULTING = "Related-Party Consulting"
    OTHER_NON_RECURRING = "Other Non-Recurring"

    # D&A
    DEPRECIATION = "Depreciation"
    AMORTISATION = "Amortisation"

    # Below EBITDA
    INTEREST_EXPENSE = "Interest Expense"
    INTEREST_INCOME = "Interest Income"
    INCOME_TAX = "Income Tax"

    # Balance Sheet — Current Assets
    CASH = "Cash & Equivalents"
    ACCOUNTS_RECEIVABLE = "Accounts Receivable"
    INVENTORY = "Inventory"
    PREPAID_EXPENSES = "Prepaid Expenses"
    OTHER_CURRENT_ASSETS = "Other Current Assets"

    # Balance Sheet — Non-current Assets
    FIXED_ASSETS = "Property Plant & Equipment"
    ACCUMULATED_DEPRECIATION = "Accumulated Depreciation"
    INTANGIBLES = "Intangible Assets"
    OTHER_NON_CURRENT_ASSETS = "Other Non-Current Assets"

    # Balance Sheet — Current Liabilities
    ACCOUNTS_PAYABLE = "Accounts Payable"
    ACCRUED_LIABILITIES = "Accrued Liabilities"
    DEFERRED_REVENUE = "Deferred Revenue"
    CURRENT_DEBT = "Current Portion of LT Debt"
    OTHER_CURRENT_LIABILITIES = "Other Current Liabilities"

    # Balance Sheet — Non-current Liabilities
    LONG_TERM_DEBT = "Long-Term Debt"
    DEFERRED_TAX = "Deferred Tax"
    OTHER_NON_CURRENT_LIABILITIES = "Other Non-Current Liabilities"

    # Equity
    SHARE_CAPITAL = "Share Capital"
    RETAINED_EARNINGS = "Retained Earnings"
    OWNER_DISTRIBUTIONS = "Owner Distributions"
    OTHER_EQUITY = "Other Equity"

    # Memo / unclassified
    MEMO = "Memo / Unclassified"


# Categories that are components of EBITDA (used to compute the EBITDA line)
EBITDA_COMPONENTS: set[ChartOfAccountsCategory] = {
    ChartOfAccountsCategory.REVENUE,
    ChartOfAccountsCategory.OTHER_INCOME,
    ChartOfAccountsCategory.COST_OF_GOODS_SOLD,
    ChartOfAccountsCategory.DIRECT_LABOUR,
    ChartOfAccountsCategory.MANUFACTURING_OVERHEAD,
    ChartOfAccountsCategory.FREIGHT_IN,
    ChartOfAccountsCategory.MANAGEMENT_COMPENSATION,
    ChartOfAccountsCategory.SALARIES_WAGES,
    ChartOfAccountsCategory.RENT_OCCUPANCY,
    ChartOfAccountsCategory.UTILITIES,
    ChartOfAccountsCategory.INSURANCE,
    ChartOfAccountsCategory.MARKETING_ADVERTISING,
    ChartOfAccountsCategory.PROFESSIONAL_FEES,
    ChartOfAccountsCategory.IT_SOFTWARE,
    ChartOfAccountsCategory.TRAVEL_ENTERTAINMENT,
    ChartOfAccountsCategory.OFFICE_EXPENSES,
    ChartOfAccountsCategory.TELECOMMUNICATIONS,
    ChartOfAccountsCategory.LEGAL_SETTLEMENTS,
    ChartOfAccountsCategory.MA_TRANSACTION_COSTS,
    ChartOfAccountsCategory.RESTRUCTURING,
    ChartOfAccountsCategory.RELATED_PARTY_CONSULTING,
    ChartOfAccountsCategory.OTHER_NON_RECURRING,
}

# Categories included in NWC = Current Assets - Current Liabilities
NWC_COMPONENTS: set[ChartOfAccountsCategory] = {
    ChartOfAccountsCategory.ACCOUNTS_RECEIVABLE,
    ChartOfAccountsCategory.INVENTORY,
    ChartOfAccountsCategory.PREPAID_EXPENSES,
    ChartOfAccountsCategory.OTHER_CURRENT_ASSETS,
    ChartOfAccountsCategory.ACCOUNTS_PAYABLE,
    ChartOfAccountsCategory.ACCRUED_LIABILITIES,
    ChartOfAccountsCategory.DEFERRED_REVENUE,
    ChartOfAccountsCategory.CURRENT_DEBT,
    ChartOfAccountsCategory.OTHER_CURRENT_LIABILITIES,
}


class RawGLLine(BaseModel):
    """A single normalised GL entry, pre-CoA mapping."""

    line_id: str = Field(description="UUID assigned on ingest; stable audit key")
    deal_id: str
    period: date = Field(description="First day of the accounting period (YYYY-MM-01)")
    account_code: str = Field(description="As-provided by client, e.g. '6001.003'")
    account_description: str
    amount: Decimal = Field(
        description=(
            "Signed net amount: positive = debit-normal (expense/asset), "
            "negative = credit-normal (revenue/liability). "
            "Never raw debit/credit split — always the economic sign."
        )
    )
    entity: str | None = None
    cost_center: str | None = None
    source_file: str = Field(description="Original filename for audit trail")
    source_row: int = Field(description="Row number in source file for audit trail")
    note: str | None = None  # Analyst or system annotation

    @model_validator(mode="after")
    def period_is_first_of_month(self) -> "RawGLLine":
        if self.period.day != 1:
            object.__setattr__(self, "period", self.period.replace(day=1))
        return self


class MappedGLLine(RawGLLine):
    """RawGLLine enriched with CoA classification."""

    standard_category: ChartOfAccountsCategory
    financial_statement: Literal["PnL", "BalanceSheet", "Memo"]
    is_ebitda_component: bool
    is_nwc_component: bool
    mapping_confidence: float = Field(ge=0.0, le=1.0)
    mapping_source: Literal["llm", "rule", "manual"]
    mapping_reasoning: str | None = None


class ValidationReport(BaseModel):
    """Result of the trial balance completeness check."""

    deal_id: str
    total_debits: Decimal
    total_credits: Decimal
    difference: Decimal
    is_balanced: bool
    tolerance: Decimal = Decimal("0.01")
    periods_checked: int
    unbalanced_periods: list[str] = Field(
        default_factory=list,
        description="Periods (YYYY-MM) where debits != credits beyond tolerance",
    )
    is_pl_only_export: bool = Field(
        default=False,
        description="True when upload contains no balance sheet accounts (1xx/2xx/3xx); imbalance may be expected",
    )
    is_mixed_export: bool = Field(
        default=False,
        description=(
            "True when upload contains both P&L activity and balance sheet snapshot rows. "
            "Global trial balance will not sum to zero (expected), so the imbalance check "
            "is relaxed. BS quality is verified per-period by the balance sheet builder."
        ),
    )
    warnings: list[str] = Field(default_factory=list)
