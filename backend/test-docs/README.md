# Test Documents — Meraqi FDD Engine

Ready-to-upload test files for manual and automated testing of the FDD pipeline.
All files represent **Acme Manufacturing Co.** across a 36-month period (Jan 2022 – Dec 2024).

---

## Folder Structure

```
test-docs/
├── general_ledger/          General Ledger files (core input to the pipeline)
├── trial_balance/           Trial Balance — one balanced, one intentionally broken
├── balance_sheet/           Monthly Balance Sheet schedule
├── income_statement/        Monthly Income Statement / P&L
├── cash_flow/               Cash Flow Statement
├── ar_ap_aging/             AR and AP Aging reports (summary + detailed)
├── supporting_schedules/    Revenue, COGS, OpEx, Payroll, Debt, Lease, etc.
└── data_room_bundles/       Pre-packaged ZIP for multi-document upload testing
```

---

## Files at a Glance

### `general_ledger/`
| File | Description |
|------|-------------|
| `gl_acme_manufacturing.csv` | 1,514-row GL — P&L entries + Balance Sheet snapshots, 36 monthly periods |
| `gl_acme_manufacturing.xlsx` | Excel version of the same GL (identical content) |
| `gl_edge_cases.csv` | GL with synthetic edge cases — tests validation and normalisation edge paths |

### `trial_balance/`
| File | Description |
|------|-------------|
| `trial_balance_balanced.csv` | Balanced trial balance — debits = credits |
| `trial_balance_unbalanced.csv` | Intentionally unbalanced — use to test the validator error path |

### `balance_sheet/`
| File | Description |
|------|-------------|
| `balance_sheet_monthly.csv` | Monthly BS schedule, 36 periods; Assets = Liabilities + Equity per period |

### `income_statement/`
| File | Description |
|------|-------------|
| `income_statement_monthly.csv` | Monthly P&L; Revenue, COGS, Gross Profit, OpEx, EBITDA |

### `cash_flow/`
| File | Description |
|------|-------------|
| `cash_flow_statement.csv` | Monthly cash flow; Operating, Investing, Financing sections |

### `ar_ap_aging/`
| File | Description |
|------|-------------|
| `ar_aging_summary.csv` | Single-row AR summary by aging bucket (0–30, 31–60, 61–90, 90+) |
| `ar_aging_detailed.csv` | Detailed AR aging by customer and invoice number |
| `ap_aging_summary.csv` | Single-row AP summary by aging bucket |
| `ap_aging_detailed.csv` | Detailed AP aging by vendor and invoice |

### `supporting_schedules/`
| File | Description |
|------|-------------|
| `revenue_schedule.csv` | Revenue by GL account |
| `cogs_schedule.csv` | Cost of Goods Sold breakdown |
| `opex_schedule.csv` | Operating Expense schedule |
| `payroll_headcount.csv` | Payroll and headcount by department |
| `debt_schedule.csv` | Debt instruments, balances, and interest |
| `lease_schedule.csv` | Lease obligations (ASC 842 / IFRS 16 style) |
| `fixed_asset_register.csv` | Fixed assets, depreciation, NBV |
| `inventory_rollforward.csv` | Inventory movement by period |
| `working_capital_schedule.csv` | NWC peg components |
| `bank_statement_cashbook.csv` | Bank statement / cashbook reconciliation |
| `equity_rollforward_cap_table.csv` | Equity rollforward and cap table |

### `data_room_bundles/`
| File | Description |
|------|-------------|
| `acme_full_data_room.zip` | ZIP bundle containing GL + AR/AP aging + projections + PDF debt agreement — use for multi-document upload testing |

---

## How to Use

**Single-file upload test:**
1. Start the backend: `cd backend && uvicorn app.main:app --reload`
2. Create a deal via `POST /api/v1/deals`
3. Upload any file above via `POST /api/v1/deals/{id}/upload`
4. Process via `POST /api/v1/deals/{id}/process`

**Multi-document test:**
Upload `data_room_bundles/acme_full_data_room.zip` — the pipeline will classify and ingest all documents in a single pass.

**Error path testing:**
Upload `trial_balance/trial_balance_unbalanced.csv` — the validator should return a `is_balanced: false` error with details.
