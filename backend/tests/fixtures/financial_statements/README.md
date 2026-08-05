# Financial Statement Fixtures

Three packages of pre-generated financial statement schedules for Acme Manufacturing Co. (Jan 2022 – Dec 2024, 36 months). These tie to the same underlying GL data as `sample_gl.csv`.

## Packages

| Directory | Contents | Purpose |
|-----------|----------|---------|
| `proper/` | Clean financials — no injected anomalies | Baseline validation; tie-out checks |
| `anomaly/` | 7 injected surface-level anomalies (see `00_injected_anomalies_manifest.csv`) | Testing anomaly detection rules |
| `anomaly_deep/` | Extended deep anomalies with an expected answer key | LLM agent evaluation and harder edge cases |

## File inventory (each package)

| File | Schedule | Source |
|------|----------|--------|
| `01_income_statement.csv` | Income Statement (monthly + annual) | Derived from GL |
| `02_balance_sheet.csv` | Balance Sheet (monthly) | Synthetic support schedules |
| `03_cash_flow_statement.csv` | Cash Flow Statement | Mixed (NI/D&A from GL, WC/CapEx generated) |
| `04_trial_balance.csv` | Trial Balance (annual period-end) | GL P&L + generated BS accounts |
| `05_general_ledger_source_copy.csv` | GL source copy | GL-derived |
| `06_ar_aging.csv` | AR Aging | Synthetic, ties to BS AR |
| `07_ap_aging.csv` | AP Aging | Synthetic, ties to BS AP |
| `08_inventory_rollforward.csv` | Inventory Rollforward | Synthetic |
| `09_fixed_asset_register.csv` | Fixed Asset Register | Synthetic |
| `10_revenue_schedule_gl_by_account.csv` | Revenue by Account | GL-derived |
| `15_debt_schedule.csv` | Debt Schedule | Synthetic |
| `16_lease_schedule.csv` | Lease Schedule | Synthetic |
| `18_working_capital_schedule.csv` | Working Capital Schedule | Synthetic |

## Usage notes

- These schedule files are **not in raw GL format** and cannot be fed directly to the ingestion pipeline today.
- They are designed for cross-document validation, anomaly detection testing (Steps 4–8), and future schedule-format ingestion support.
- For direct ingestion tests, use `backend/tests/fixtures/sample_gl.csv` (raw GL format with both P&L and BalanceSheet rows).
