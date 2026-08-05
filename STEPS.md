# FDD Engine — Step-by-Step Implementation Tracker

## How We Work
- One step at a time. Build → Test manually → Confirm → Advance.
- Cloud-ready architecture from the start (local POC now, cloud later).
- Big 4 quality bar: every financial calculation is traceable to source data.
- LLM agents are mocked until an Anthropic API key is available.

---

## STEP 1 — Backend Foundation
**Status: PENDING**

Foundation exists on fork (FastAPI, deal store, upload/process API, pipeline orchestrator) but this step is not formally signed off in the tracker.

### Manual Test Checklist
- [x] `cd backend && pip install -e ".[dev]"` runs without errors
- [x] `uvicorn app.main:app --reload` starts without errors
- [x] `GET http://localhost:8000/health` returns `{"status": "ok"}`
- [x] `POST http://localhost:8000/api/v1/deals` returns `deal_id`
- [x] `POST http://localhost:8000/api/v1/deals/{deal_id}/upload` accepts files
- [x] `POST http://localhost:8000/api/v1/deals/{deal_id}/process` triggers pipeline
- [x] `GET http://localhost:8000/api/v1/deals/{deal_id}/status` returns status JSON
- [ ] Formal Step 1 sign-off recorded in tracker

---

## STEP 2 — Data Ingestion Pipeline
**Status: COMPLETE**

**Goal:** GL CSV/Excel files are loaded, normalized, and validated. Trial balance check passes. Multi-document data room intake supported.

Files: `pipeline/ingestion/loader.py`, `normalizer.py`, `validator.py`, `document_registry.py`, `zip_extractor.py`, aging/projections parsers, `schemas/gl.py`

### Test Checklist
- [x] Upload `tests/fixtures/sample_gl.csv` → process → normalized GL lines returned
- [x] Unbalanced trial balance file returns validation error with details
- [x] Excel (.xlsx) file processes identically to CSV
- [x] Multi-file / ZIP data room upload classifies and ingests AR/AP aging, projections, PDF debt agreements
- [x] `GET /api/v1/deals/{id}/documents` returns document inventory
- [x] Cross-document AR/AP aging tie-outs vs GL balance sheet

---

## STEP 3 — Chart of Accounts Mapper + Financial Statement Builder
**Status: COMPLETE**

CoA mapper agent, P&L / Balance Sheet / Cash Flow builders, and `GET /financials/*` API endpoints fully implemented and tested.

### Test Checklist
- [x] `GET /api/v1/deals/{id}/financials/pnl?period=annual` returns 3 annual periods (2022–2024)
- [x] Revenue + COGS = Gross Profit (exactly, to the cent) — asserted in `TestPnLBuilder`
- [x] Balance Sheet balances: Assets == Liabilities + Equity in every period — asserted in `TestBalanceSheetBuilder` and `TestBalanceSheetEndpoint`
- [x] Mock mode works without Anthropic API key — all 125 tests pass with `USE_MOCK_LLM=true`

### Architecture notes
- `backend/tests/fixtures/generate_fixtures.py` extended to emit 612 monthly BalanceSheet rows (17 accounts × 36 periods) alongside the existing 902 P&L rows; totals 1,514 rows
- Synthetic BS rows are balanced per-period via a Retained Earnings plug (Assets = Liabilities + Equity within $0.05)
- Validator extended with `is_mixed_export` flag: mixed P&L-activity + BS-snapshot uploads pass the ingestion check (BS quality enforced per-period by the builder)
- Root `tests/` folder relocated to `backend/tests/fixtures/financial_statements/{proper,anomaly,anomaly_deep}` and removed from `.gitignore`
- `GET /financials/pnl?period=annual` rolls up 36 monthly rows into 3 annual periods; summary dicts keyed by "YYYY"

---

## STEP 4 — QoE Engine + Red Flag Detector
**Status: COMPLETE**

QoE rules engine, waterfall, red flag detector, LLM reviewer/enrichment agents, and API endpoints fully implemented and tested.

### Test Checklist
- [x] Planted legal settlement in fixture GL detected as one-time item — asserted in `TestQoERules` and `TestQoEOrchestrator`
- [x] Owner comp excess detected across all 36 months — asserted in `TestQoERules.test_owner_comp_excess_detected_all_36_periods`
- [x] `GET /api/v1/deals/{id}/qoe` waterfall array sums correctly — asserted in `TestQoEEndpoint.test_qoe_waterfall_base_plus_bars_equals_result`
- [x] `GET /api/v1/deals/{id}/redflags` returns ≥3 flags with correct severity — asserted in `TestRedFlagEndpoint`

### Architecture notes
- All pipeline logic was pre-existing; Step 4 sign-off added orchestrator integration tests (`TestQoEOrchestrator`) and API-level HTTP tests (`test_api/test_qoe_redflags.py`, 23 tests)
- `TestRedFlagRulesWithBSCF` verifies that `detect_all()` accepts and handles `balance_sheet` / `cash_flow` arguments without error; BS/CF-dependent rules don't breach thresholds in the synthetic fixture (AR days ~10d, DR growing, cash conversion healthy)
- Mock LLM agents inject diligence questions on all High/Medium flags — verified end-to-end in `test_high_medium_flags_have_diligence_questions`

---

## STEP 5 — React Frontend Dashboard
**Status: COMPLETE**

Next.js upload page, QoE Center, Red Flag Center wired to backend; upload accepts ZIP; reports page has backend databook download (local).

`NEXT_PUBLIC_API_BASE_URL` now drives `fdd-client.ts` (defaults to `localhost:8000`; see `frontend/.env.example`). Extended with typed wrappers for NWC, commercial health, net debt, DCF, contracts, narrative, tie-outs, P&L/BS/CF.

Live-data wiring, page by page — **when a `dealId` is selected, every page below branches to a real-backend view and never falls through to the seeded mock demo data**; the mock BFF routes (`/api/deal/*`) remain only as the no-deal-selected demo experience:
- [x] Dashboard: `DealSummaryBanner` (LTM revenue, adjusted EBITDA, margin, NWC peg, net debt, red flag counts), `JuniorAnalystReport` (real narrative), `RealDashboard` (revenue/EBITDA trend, top red flags, deal navigation)
- [x] Financial Analysis: QoE sub-tab (`QoeCenter`, pre-existing), Working Capital sub-tab (`NWCPanel` — real pegs/ratios/trend), Cash Flow sub-tab (`CashFlowPanel`), Statements sub-tab (`StatementsPanel` — real P&L/BS); Revenue QoE and Margin/Cost sub-tabs show an honest "requires customer-level/cost-category data this system does not ingest" card instead of the old fabricated multipliers
- [x] Risk Assessment: `RedFlagCenter` (pre-existing) + `TieOutsPanel` (real AR/AP-vs-GL reconciliation) + `NetDebtPanel`; the old gauge/risk-register/anomaly-monitor mock block is replaced with an honest note (requires bank statement/payroll ingestion not yet implemented) rather than shown alongside real numbers
- [x] Documents: `DocumentsPanel` (real document inventory + parse status/confidence) + `ContractsPanel` (real contract instruments/clauses, with a re-analyze button)
- [x] Customer Analytics: honest "requires customer-level invoice data" card (no customer schema exists in this system — not approximated)
- [x] Reports: databook export unchanged; `JuniorAnalystReport` embedded; report readiness derived from real red flags + tie-outs instead of the mock risk/inquiry queries; the old Export Center/pack (self-labeled "(mock)" in its own content) is now shown only in the no-deal demo view
- [x] Inquiry: honest banner noting the inquiry/decision-queue tracker is a local demo workflow, not backend-persisted per deal (no inquiry persistence layer exists in this system)
- [x] New backend endpoint `GET /api/v1/deals/{id}/tie-outs` added to support the real tie-out panel (reads `cross_document_validation.json`, already computed during ingestion)

### Test Checklist
- [x] `npm run build` compiles cleanly (`next build` — 0 errors, 0 warnings)
- [x] Upload page accepts CSV/ZIP, polls status, shows "Complete" (pre-existing, unchanged)
- [x] QoE Center renders waterfall chart with clickable bars (pre-existing, unchanged)
- [x] Red Flag table shows High/Medium/Low badges, sortable by severity (pre-existing, unchanged)

### Architecture notes
- Chose page-level branching (`if (dealId) { return <RealX .../> }`) over reshaping backend data into the legacy mock `SummaryResponseSchema`/`AnalysisResponseSchema`/`RiskResponseSchema` shapes. Forcing real numbers through the mock schema would require fake `lineage`/`cellTrace`/`benchmark` filler for fields with no backend equivalent — a worse outcome than a clean, honest real view. The mock BFF routes (`app/api/deal/*`) are unchanged and untouched; they remain reachable only from the no-deal demo path.
- `npm run lint`/`build` type-checks the whole app on every change in this pass — no `any`-typed escape hatches were needed.

---

## STEP 6 — NWC Analyzer + Commercial Health
**Status: COMPLETE**

- [x] Full NWC peg calculation — `ltm_average`, `median_trailing_12`, `seasonal_adjusted` (when ≥24 months of history), with a deterministic recommended-method + rationale
- [x] NWC data points built from the balance sheet's `NWC_COMPONENTS` categories (schemas/gl.py), so every figure traces to source GL lines through the existing balance sheet builder
- [x] Working-capital ratios: DSO, DPO, DIO, cash conversion cycle, AR/AP >60-day % (graceful `partial` status when aging not uploaded)
- [x] Commercial health analyzer — revenue growth YoY, gross/EBITDA margin trend, revenue volatility, Q4 seasonality check; customer-level metrics (concentration, churn, customer count) explicitly marked `unavailable_metrics` rather than approximated, since this system does not ingest customer-level revenue data
- [x] `GET /api/v1/deals/{id}/nwc` and `GET /api/v1/deals/{id}/commercial`
- [x] Two new red-flag rules wired in: `NWC_VOLATILITY` (std/mean > 30%) and `REVENUE_SEASONALITY` (Q4 > 40% of annual revenue, informational) — `nwc_analyzer` moved before `redflag_detector` in the default stage order so the volatility rule has data to run against
- [x] 21 new tests: `backend/tests/test_pipeline/test_nwc_analyzer.py` (peg math, degradation paths, red-flag rules, full HTTP flow)

### Architecture notes
- `CUSTOMER_CONCENTRATION` and `CUSTOMER_COUNT_DECLINE` red-flag rules from `plan.txt` are intentionally NOT implemented — they require customer-level revenue data this system does not ingest, and approximating them from aggregate GL would violate the no-invented-numbers rule

---

## STEP 7 — PDF Contract Parser
**Status: COMPLETE**

- [x] PDF text extraction (pdfplumber) in ingestion
- [x] Mock LLM debt instrument extraction grounded in PDF text (heuristic; no filename fiction)
- [x] Digital PDF fixture + ingestion tests asserting `debt_instruments.json` terms match document content
- [x] Full contract clause analysis: `change_of_control_clause`, `prepayment_terms`, `events_of_default`, `material_obligations` (enumerated list) added to `DebtInstrument` (`schemas/contracts.py`), extracted via grounded heuristics in `agents/contract_parser.py` and mirrored in the real-LLM tool schema/prompt
- [x] `POST /api/v1/deals/{id}/contracts/analyze` — re-runs extraction over all uploaded debt agreement/contract PDFs on demand (`pipeline/contracts/orchestrator.py`)
- [x] `GET /api/v1/deals/{id}/contracts` — instruments + a flattened `ContractClause` list (clause_type, summary, source_document, instrument_id) for the Documents/Risk UI; falls back to ingestion-time `debt_instruments.json` if `/analyze` was never explicitly called, so a normal `/process` run is sufficient
- [ ] OCR path for scanned PDFs — explicitly out of scope; this system parses digital (text-extractable) PDFs only and fails clearly (not silently) on scanned/image PDFs
- [x] Credit agreement fixture (`Credit_Agreement_FNB.pdf`) extended with Change of Control, Prepayment, and Affirmative Covenants articles so the new heuristics are tested against real grounded PDF text, not synthetic strings
- [x] 10 new tests: `backend/tests/test_pipeline/test_contract_analysis.py`

---

## STEP 6b — Net Debt Bridge + Simple DCF
**Status: COMPLETE**

- [x] Net debt bridge computed deterministically from the balance sheet (Cash, Current Debt, Long-Term Debt categories, latest period) — `GET /api/v1/deals/{id}/net-debt`
- [x] Bridge waterfall components (Current Debt, LT Debt, Total Debt, Less Cash, Net Debt) sum to the reported net debt figure
- [x] Contract-extracted instrument detail (lender, rate, maturity, covenants) attached as supplementary schedule detail from `debt_instruments.json`, reconciled against the GL-derived total debt with a 5% tolerance note — never used to recompute totals (avoids double-counting between ledger and contract-text sources)
- [x] Net Debt / LTM EBITDA multiple
- [x] Simple, disclosed-assumption DCF (`GET /api/v1/deals/{id}/dcf`) — unlevered FCF = EBITDA − Capex, Gordon-growth terminal value, default 12% discount / 2% terminal growth clearly labeled as assumptions (not deal-specific WACC) with a `limitations` list on every response. Directional cross-check only, per plan.txt guidance to prefer net debt + NWC over a "fancy" DCF
- [x] 12 new tests: `backend/tests/test_pipeline/test_net_debt_and_dcf.py`

---

## STEP 8 — Databook Export + Narrative Drafter
**Status: BACKEND COMPLETE / FRONTEND WIRING PENDING**

- [x] Excel databook export (`POST /api/v1/deals/{id}/databook/export`) — QoE waterfall, adjustments, GL mapping, aging, tie-outs, IRL tabs (local)
- [x] `NarrativeDrafterAgent` (`agents/narrative_drafter.py`, mock + real) — drafts 5 sections (executive summary, key risks, QoE highlights, working capital, recommendations) from a fact sheet of already-computed figures (financials, QoE, red flags, NWC, net debt). Never receives raw GL data or performs arithmetic; every figure quoted in a section traces back to `figures_used` on the persisted report
- [x] `pipeline/narrative/orchestrator.py` — builds the fact sheet, runs as the final pipeline stage (`narrative_drafter`, after net_debt_bridge), degrades gracefully (`partial` + `data_gaps` list) when red flags/NWC/net debt are unavailable, `skipped` only when financials/QoE (the two hard requirements) are missing
- [x] `POST /api/v1/deals/{id}/narrative/generate` and `GET /api/v1/deals/{id}/narrative`
- [x] 8 new tests: `backend/tests/test_pipeline/test_narrative_drafter.py` (fact sheet gaps, mock-narrative grounding — every figure quoted must appear in figures_used, full HTTP flow)
- [ ] Frontend: replace `junior-analyst-report.tsx` `PLACEHOLDER_SECTIONS` with live narrative, wire Regenerate button to `POST /narrative/generate`, enable PDF export — tracked under Step 5 frontend wiring

---

## Architecture Decisions Log
| Date | Decision | Reason |
|------|----------|--------|
| 2026-05-28 | JSON file storage (not DB) for POC | Local dev simplicity; will swap to PostgreSQL for cloud deployment |
| 2026-05-28 | Mock LLM agents by default | No API key yet; enables full pipeline testing without cost |
| 2026-05-28 | Python Decimal for all financial amounts | Prevents floating-point drift in financial calculations |
| 2026-05-28 | Amounts serialized as strings in JSON | Frontend parses to number only for display; preserves precision |
| 2026-05-28 | FastAPI BackgroundTasks for processing | Sufficient for <50K row files; will replace with Celery+Redis for cloud |
| 2026-06-08 | Multi-document ingestion in single `ingestion` stage | Classify and route GL, aging, projections, PDFs; optional docs non-blocking |
| 2026-06-08 | `.xls` removed until xlrd dependency needed | Avoid broken loader path; `.xlsx` and CSV cover POC |
| 2026-06-24 | Synthetic BS rows in generator (not schedule conversion) | Faster, self-contained; schedule files deferred to Steps 4–8 validation work |
| 2026-06-24 | `is_mixed_export` validator flag instead of raising on global TB imbalance | P&L + BS snapshot file won't sum to zero globally; BS quality enforced per-period by builder |
| 2026-06-24 | Annual P&L rollup in API layer (not stored) | Keep storage simple (monthly JSON); rollup is cheap at query time |
| 2026-06-24 | BS/CF red-flag rules non-blocking (optional args) | Gracefully degrades to P&L-only flags when BS/CF unavailable; rules don't breach thresholds in synthetic fixture but are exercised in tests |
