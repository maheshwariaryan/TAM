"""
Chart of Accounts Mapper Agent.

Maps raw (account_code, account_description) pairs to standardised
ChartOfAccountsCategory values using OpenAI function calling.

Design:
  - Batches up to 30 unique account pairs per API call to minimise cost
  - System prompt carries the full taxonomy (reused across calls)
  - Structured output via function calling — no JSON parsing errors
  - Mock mode returns a deterministic rule-based mapping using account code prefixes,
    which is sufficient for the fixture data and avoids any API cost during dev

Golden rule enforced: this agent outputs a classification dict only.
No arithmetic, no amounts, no DataFrames touch this code.
"""

import logging
from typing import Any

from app.agents.base import AgentError, BaseAgent
from app.schemas.gl import ChartOfAccountsCategory

logger = logging.getLogger(__name__)

# Maximum account pairs to send in a single API call
_BATCH_SIZE = 30

# Full taxonomy description sent as the system prompt.
# Kept in one place so it's easy to update as we add categories.
_SYSTEM_PROMPT = """You are a senior financial analyst at a Big 4 accounting firm specialising
in M&A Transaction Advisory Services. Your task is to classify general ledger account codes
into standardised categories for financial due diligence analysis.

You will be given a list of (account_code, account_description) pairs from a client's
chart of accounts and must map each to exactly one category from the taxonomy below.

TAXONOMY:
- Revenue: Product/service sales, any top-line income
- Other Income: Interest income, gains on disposal, non-operating income
- Cost of Goods Sold: Direct material costs, purchased goods for resale
- Direct Labour: Production/manufacturing wages directly tied to output
- Manufacturing Overhead: Factory rent, utilities, indirect manufacturing costs
- Freight In: Inbound shipping and logistics costs
- Management Compensation: Salaries/bonuses for owners, directors, senior management
- Salaries & Wages: All other employee compensation (non-management)
- Rent & Occupancy: Office/facility rent, property costs
- Utilities: Electricity, gas, water for offices/facilities
- Insurance: Business insurance premiums
- Marketing & Advertising: All promotional and marketing spend
- Professional Fees: Legal, accounting, consulting (third-party, arm's length)
- IT & Software: Technology, SaaS subscriptions, IT support
- Travel & Entertainment: Business travel, client entertainment
- Office Expenses: Stationery, office supplies, minor equipment
- Telecommunications: Phone, internet, communications
- Legal Settlements: One-time legal settlements, court awards, regulatory fines
- M&A Transaction Costs: Advisory fees, due diligence costs, deal-related legal fees
- Restructuring Charges: Redundancy costs, site closure costs
- Related-Party Consulting: Consulting or management fees paid to related parties/owner entities
- Other Non-Recurring: Any other clearly non-recurring charge not in above categories
- Depreciation: Depreciation of fixed assets
- Amortisation: Amortisation of intangible assets
- Interest Expense: Debt interest, finance charges
- Income Tax: Current and deferred income tax charges
- Cash & Equivalents: Cash, bank accounts, short-term deposits
- Accounts Receivable: Trade debtors, amounts owed by customers
- Inventory: Raw materials, WIP, finished goods
- Prepaid Expenses: Prepaid costs, deposits
- Other Current Assets: Other short-term assets
- Property Plant & Equipment: Fixed assets, machinery, vehicles, leasehold improvements
- Accumulated Depreciation: Contra-asset: accumulated depreciation
- Intangible Assets: Patents, trademarks, goodwill, customer lists
- Other Non-Current Assets: Other long-term assets
- Accounts Payable: Trade creditors, amounts owed to suppliers
- Accrued Liabilities: Accrued expenses, provisions
- Deferred Revenue: Customer deposits, unearned income
- Current Portion of LT Debt: Current portion of loans/leases due within 12 months
- Other Current Liabilities: Other short-term liabilities
- Long-Term Debt: Bank loans, bonds, finance leases > 12 months
- Deferred Tax: Deferred tax liability/asset
- Other Non-Current Liabilities: Other long-term liabilities
- Share Capital: Issued share capital, paid-in capital
- Retained Earnings: Accumulated retained earnings/deficit
- Owner Distributions: Dividends, drawings, distributions to shareholders
- Other Equity: Other equity components
- Memo / Unclassified: Use ONLY if the account genuinely cannot be classified

RULES:
1. Use "Management Compensation" for owner/director pay — this is critical for QoE analysis
2. Use "Related-Party Consulting" for any consulting/management fees to related entities
3. Use "Legal Settlements" for one-time legal costs — NOT for recurring legal/professional fees
4. Use "M&A Transaction Costs" for deal advisory, due diligence, transaction legal fees
5. When uncertain between two close categories, choose the more specific one
6. Never return "Memo / Unclassified" unless you have genuinely no basis to classify
"""

# OpenAI function definition for structured output
_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "classify_accounts",
            "description": "Return the classification for each account code provided.",
            "parameters": {
                "type": "object",
                "properties": {
                    "classifications": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "account_code": {"type": "string"},
                                "category": {
                                    "type": "string",
                                    "description": "Exact category name from the taxonomy",
                                },
                                "financial_statement": {
                                    "type": "string",
                                    "enum": ["PnL", "BalanceSheet", "Memo"],
                                },
                                "confidence": {
                                    "type": "number",
                                    "minimum": 0,
                                    "maximum": 1,
                                },
                                "reasoning": {
                                    "type": "string",
                                    "description": "One sentence explaining the classification",
                                },
                            },
                            "required": ["account_code", "category", "financial_statement",
                                         "confidence", "reasoning"],
                        },
                    }
                },
                "required": ["classifications"],
            },
        },
    }
]

# ── Mock mapping ─────────────────────────────────────────────────────────────
# Rule-based, covers the Acme fixture perfectly. Good enough for all dev/test work.
_MOCK_PREFIX_MAP: dict[str, tuple[ChartOfAccountsCategory, str]] = {
    "4": (ChartOfAccountsCategory.REVENUE,                "PnL"),
    "5": (ChartOfAccountsCategory.COST_OF_GOODS_SOLD,     "PnL"),
    "6001": (ChartOfAccountsCategory.MANAGEMENT_COMPENSATION, "PnL"),
    "6097": (ChartOfAccountsCategory.RELATED_PARTY_CONSULTING, "PnL"),
    "6098": (ChartOfAccountsCategory.MA_TRANSACTION_COSTS,    "PnL"),
    "6099": (ChartOfAccountsCategory.LEGAL_SETTLEMENTS,       "PnL"),
    "6002": (ChartOfAccountsCategory.SALARIES_WAGES,          "PnL"),
    "6003": (ChartOfAccountsCategory.RENT_OCCUPANCY,          "PnL"),
    "6004": (ChartOfAccountsCategory.UTILITIES,               "PnL"),
    "6005": (ChartOfAccountsCategory.INSURANCE,               "PnL"),
    "6006": (ChartOfAccountsCategory.MARKETING_ADVERTISING,   "PnL"),
    "6007": (ChartOfAccountsCategory.PROFESSIONAL_FEES,       "PnL"),
    "6008": (ChartOfAccountsCategory.IT_SOFTWARE,             "PnL"),
    "6009": (ChartOfAccountsCategory.TRAVEL_ENTERTAINMENT,    "PnL"),
    "601":  (ChartOfAccountsCategory.OFFICE_EXPENSES,         "PnL"),   # 6010, 6011
    "7001": (ChartOfAccountsCategory.DEPRECIATION,            "PnL"),
    "7002": (ChartOfAccountsCategory.AMORTISATION,            "PnL"),
    "8001": (ChartOfAccountsCategory.INTEREST_EXPENSE,        "PnL"),
    "8002": (ChartOfAccountsCategory.INCOME_TAX,              "PnL"),
    "1001": (ChartOfAccountsCategory.CASH,                    "BalanceSheet"),
    "1002": (ChartOfAccountsCategory.ACCOUNTS_RECEIVABLE,     "BalanceSheet"),
    "1003": (ChartOfAccountsCategory.INVENTORY,               "BalanceSheet"),
    "1004": (ChartOfAccountsCategory.INVENTORY,               "BalanceSheet"),
    "1005": (ChartOfAccountsCategory.PREPAID_EXPENSES,        "BalanceSheet"),
    "1006": (ChartOfAccountsCategory.FIXED_ASSETS,            "BalanceSheet"),
    "1007": (ChartOfAccountsCategory.ACCUMULATED_DEPRECIATION,"BalanceSheet"),
    "1008": (ChartOfAccountsCategory.INTANGIBLES,             "BalanceSheet"),
    "2001": (ChartOfAccountsCategory.ACCOUNTS_PAYABLE,        "BalanceSheet"),
    "2002": (ChartOfAccountsCategory.ACCRUED_LIABILITIES,     "BalanceSheet"),
    "2003": (ChartOfAccountsCategory.DEFERRED_REVENUE,        "BalanceSheet"),
    "2004": (ChartOfAccountsCategory.CURRENT_DEBT,            "BalanceSheet"),
    "2005": (ChartOfAccountsCategory.LONG_TERM_DEBT,          "BalanceSheet"),
    "2006": (ChartOfAccountsCategory.DEFERRED_TAX,            "BalanceSheet"),
    "3001": (ChartOfAccountsCategory.SHARE_CAPITAL,           "BalanceSheet"),
    "3002": (ChartOfAccountsCategory.RETAINED_EARNINGS,       "BalanceSheet"),
    "3003": (ChartOfAccountsCategory.OWNER_DISTRIBUTIONS,     "BalanceSheet"),
}


def _mock_classify(account_code: str) -> tuple[ChartOfAccountsCategory, str]:
    """Deterministic mock classification by account code prefix (longest match wins)."""
    for length in (4, 3, 2, 1):
        prefix = account_code[:length]
        if prefix in _MOCK_PREFIX_MAP:
            return _MOCK_PREFIX_MAP[prefix]
    return (ChartOfAccountsCategory.MEMO, "Memo")


class CoAMapperAgent(BaseAgent):
    name = "CoAMapper"
    _tools = _TOOLS

    async def map_accounts(
        self, pairs: list[tuple[str, str]]
    ) -> dict[str, dict]:
        """
        Classify a list of (account_code, account_description) pairs.

        Returns:
            {account_code: {"category": ChartOfAccountsCategory, "financial_statement": str,
                            "confidence": float, "reasoning": str}}
        """
        result: dict[str, dict] = {}

        # Process in batches to keep prompt size manageable
        for i in range(0, len(pairs), _BATCH_SIZE):
            batch = pairs[i : i + _BATCH_SIZE]
            logger.info(
                "[CoAMapper] classifying batch %d-%d of %d accounts",
                i + 1, min(i + _BATCH_SIZE, len(pairs)), len(pairs),
            )
            batch_result = await self.run(batch)
            result.update(batch_result)

        return result

    def _build_messages(self, payload: list[tuple[str, str]]) -> list[dict]:
        account_list = "\n".join(
            f"  {i+1}. code={code!r}  description={desc!r}"
            for i, (code, desc) in enumerate(payload)
        )
        return [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Classify the following {len(payload)} GL accounts:\n\n"
                    f"{account_list}\n\n"
                    "Call the classify_accounts function with your results."
                ),
            },
        ]

    def _parse_response(self, response: Any) -> dict[str, dict]:
        tool_use = next((b for b in response.content if b.type == "tool_use"), None)
        if not tool_use:
            raise AgentError("[CoAMapper] no tool call in response — cannot extract classifications")

        data = tool_use.input
        out: dict[str, dict] = {}
        for item in data.get("classifications", []):
            code = item["account_code"]
            # Validate category against our enum
            try:
                category = ChartOfAccountsCategory(item["category"])
            except ValueError:
                logger.warning("[CoAMapper] unknown category %r for code %s — using MEMO", item["category"], code)
                category = ChartOfAccountsCategory.MEMO
            out[code] = {
                "category": category,
                "financial_statement": item.get("financial_statement", "Memo"),
                "confidence": float(item.get("confidence", 0.8)),
                "reasoning": item.get("reasoning", ""),
            }
        return out

    def _mock_response(self, payload: list[tuple[str, str]]) -> dict[str, dict]:
        return {
            code: {
                "category": cat,
                "financial_statement": stmt,
                "confidence": 1.0,
                "reasoning": f"Mock: prefix-based classification for account {code}",
            }
            for code, _ in payload
            for cat, stmt in [_mock_classify(code)]
        }
