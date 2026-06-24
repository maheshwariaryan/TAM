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
**Status: PENDING**

Partial work complete: QoE rules engine, waterfall, red flag detector, LLM reviewer/enrichment agents, and API endpoints exist.

### Test Checklist
- [ ] Planted legal settlement in fixture GL detected as one-time item
- [ ] Owner comp excess detected across all 36 months
- [ ] `GET /api/v1/deals/{id}/qoe` waterfall array sums correctly
- [ ] `GET /api/v1/deals/{id}/redflags` returns ≥3 flags with correct severity

---

## STEP 5 — React Frontend Dashboard
**Status: PENDING**

Partial work complete: Next.js upload page, QoE Center, Red Flag Center wired to backend; upload accepts ZIP; reports page has backend databook download (local).

### Test Checklist
- [ ] `npm run dev` starts without errors
- [ ] Upload page accepts CSV/ZIP, polls status, shows "Complete"
- [ ] QoE Center renders waterfall chart with clickable bars
- [ ] Red Flag table shows High/Medium/Low badges, sortable by severity

---

## STEP 6 — NWC Analyzer + Commercial Health
**Status: PENDING**

Partial work complete:
- [x] `nwc_analyzer` pipeline stage stub (validates AR/AP aging inputs ingested)
- [ ] Full NWC peg calculation
- [ ] Commercial health analyzer
- [ ] `GET /api/v1/deals/{id}/nwc`

---

## STEP 7 — PDF Contract Parser
**Status: PENDING**

Partial work complete:
- [x] PDF text extraction (pdfplumber) in ingestion
- [x] Mock LLM debt instrument extraction from PDF agreements
- [ ] Full contract clause analysis and obligations parsing
- [ ] `POST /api/v1/deals/{id}/contracts/analyze`

---

## STEP 8 — Databook Export + Narrative Drafter
**Status: PENDING**

Partial work complete:
- [x] Excel databook export (`POST /api/v1/deals/{id}/databook/export`) — QoE waterfall, adjustments, GL mapping, aging, tie-outs, IRL tabs (local)
- [ ] Narrative drafter (executive summary generation)
- [ ] PDF report generation from backend

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
