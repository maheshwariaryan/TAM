/**
 * FDD Engine API client — wraps all calls to the FastAPI backend.
 * Base URL comes from NEXT_PUBLIC_API_BASE_URL (defaults to localhost:8000 for local dev).
 *
 * All amounts come back as strings (Decimal) and are parsed to number here
 * only for display. Arithmetic on financial figures must use the raw string
 * values or the backend.
 */

const BASE = `${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"}/api/v1`;

// `credentials: "include"` sends the httpOnly session cookie set by
// POST /auth/login|signup on every request — required because the frontend
// (localhost:3000) and backend (localhost:8000) are different origins.
async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { credentials: "include" });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`GET ${path} → ${res.status}: ${body}`);
  }
  return res.json();
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
    credentials: "include",
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`POST ${path} → ${res.status}: ${text}`);
  }
  return res.json();
}

async function put<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    credentials: "include",
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`PUT ${path} → ${res.status}: ${text}`);
  }
  return res.json();
}

async function patch<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    credentials: "include",
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`PATCH ${path} → ${res.status}: ${text}`);
  }
  return res.json();
}

// ─── Auth ────────────────────────────────────────────────────────────────────
// These call FastAPI's /api/v1/auth/* endpoints directly (not the old Next.js
// mock routes) and return a plain {ok, ...} shape so the calling page can show
// `message` on failure without needing to catch a thrown Error.

export interface AuthUser {
  id: string;
  email: string;
  full_name: string;
  created_at: string;
}

async function authRequest<T extends object>(
  path: string,
  body: unknown
): Promise<{ ok: true } & T | { ok: false; message: string }> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    credentials: "include",
  });
  let json: Record<string, unknown> = {};
  try {
    json = await res.json();
  } catch {
    // no body / not JSON — fall through with an empty object
  }
  if (!res.ok) {
    const detail = json.detail;
    const message = Array.isArray(detail)
      ? detail.map((d) => (d as { msg?: string }).msg).filter(Boolean).join(", ")
      : typeof detail === "string"
        ? detail
        : `Request failed (HTTP ${res.status})`;
    return { ok: false, message };
  }
  return { ok: true, ...(json as T) };
}

// signup/login return UserPublic's fields directly on the response body (not
// wrapped), so AuthUser's fields end up spread onto the result alongside `ok`.
export const signup = (email: string, password: string, fullName: string) =>
  authRequest<AuthUser>("/auth/signup", { email, password, full_name: fullName });

export const login = (email: string, password: string) =>
  authRequest<AuthUser>("/auth/login", { email, password });

export async function logout(): Promise<void> {
  await fetch(`${BASE}/auth/logout`, { method: "POST", credentials: "include" });
}

export async function getCurrentUser(): Promise<AuthUser | null> {
  const res = await fetch(`${BASE}/auth/me`, { credentials: "include" });
  if (!res.ok) return null;
  return res.json();
}

export const forgotPassword = (email: string) =>
  authRequest<{ message: string; reset_token: string; reset_url: string }>(
    "/auth/forgot-password",
    { email }
  );

export const resetPassword = (token: string, newPassword: string) =>
  authRequest<Record<string, never>>("/auth/reset-password", { token, new_password: newPassword });

// ─── Deal lifecycle ──────────────────────────────────────────────────────────

export interface DealStages {
  ingestion: string;
  coa_mapping: string;
  financial_builder: string;
  qoe_engine: string;
  redflag_detector: string;
  nwc_analyzer?: string;
  dcf_engine?: string;
  net_debt_bridge?: string;
}

export interface UploadedFile {
  filename: string;
  stored_path: string;
  size_bytes: number;
  uploaded_at: string;
}

export interface Deal {
  deal_id: string;
  company_name: string;
  deal_name: string;
  currency: string;
  created_at: string;
  updated_at: string;
  stages: DealStages;
  progress_pct: number;
  uploaded_files: UploadedFile[];
  error: string | null;
}

export const createDeal = (company_name: string, deal_name: string, currency = "USD") =>
  post<Deal>("/deals", { company_name, deal_name, currency });

export const listDeals = () => get<Deal[]>("/deals");

export const getDeal = (id: string) => get<Deal>(`/deals/${id}`);

export const getDealStatus = (id: string) => get<Deal>(`/deals/${id}/status`);

export async function uploadFiles(dealId: string, files: File[]): Promise<{ files_received: number }> {
  const form = new FormData();
  files.forEach((f) => form.append("files", f));
  const res = await fetch(`${BASE}/deals/${dealId}/upload`, {
    method: "POST",
    body: form,
    credentials: "include",
  });
  if (!res.ok) throw new Error(`Upload failed: ${await res.text()}`);
  return res.json();
}

export const processDeal = (dealId: string, stages?: string[]) =>
  post<{ message: string; stages_queued: string[] }>(`/deals/${dealId}/process`, stages ? { stages } : {});

// ─── Financial statements ─────────────────────────────────────────────────────

export interface FinancialSummary {
  deal_id: string;
  periods: string[];
  revenue: Record<string, string>;
  ebitda: Record<string, string>;
  ebitda_margin_pct: Record<string, number>;
  gross_margin_pct: Record<string, number>;
}

export const getFinancialSummary = (dealId: string) =>
  get<FinancialSummary>(`/deals/${dealId}/financials/summary`);

export interface PnLStatement {
  deal_id: string;
  periods: string[];
  revenue: Record<string, string>;
  gross_profit: Record<string, string>;
  ebitda: Record<string, string>;
  ebit: Record<string, string>;
  net_income: Record<string, string>;
  gross_margin: Record<string, number>;
  ebitda_margin: Record<string, number>;
}

export const getPnL = (dealId: string, period?: string) =>
  get<PnLStatement>(`/deals/${dealId}/financials/pnl${period ? `?period=${period}` : ""}`);

export interface BalanceSheetRow {
  period: string;
  category: string;
  label: string;
  amount: string;
  section: string;
}

export interface BalanceSheet {
  deal_id: string;
  periods: string[];
  rows: BalanceSheetRow[];
  total_assets: Record<string, string>;
  total_liabilities: Record<string, string>;
  total_equity: Record<string, string>;
  is_balanced: Record<string, boolean>;
}

export const getBalanceSheet = (dealId: string) =>
  get<BalanceSheet>(`/deals/${dealId}/financials/balance-sheet`);

export interface CashFlowStatement {
  deal_id: string;
  periods: string[];
  operating_cash_flow: Record<string, string>;
  investing_cash_flow: Record<string, string>;
  financing_cash_flow: Record<string, string>;
  net_cash_flow: Record<string, string>;
  cash_conversion: Record<string, number | null>;
}

export const getCashFlow = (dealId: string) =>
  get<CashFlowStatement>(`/deals/${dealId}/financials/cash-flow`);

// ─── QoE ─────────────────────────────────────────────────────────────────────

export interface WaterfallItem {
  label: string;
  amount: string;
  type: "base" | "addback" | "deduction" | "result";
  adjustment_ids: string[];
}

export interface QoEAdjustment {
  adjustment_id: string;
  deal_id: string;
  period: string;
  label: string;
  category: string;
  direction: "add_back" | "deduction";
  reported_amount: string;
  adjustment_amount: string;
  normalized_amount: string;
  source_gl_line_ids: string[];
  detection_method: string;
  rule_triggered: string | null;
  llm_reviewed: boolean;
  llm_reasoning: string | null;
}

export interface QoEReport {
  deal_id: string;
  reported_ebitda: Record<string, string>;
  adjusted_ebitda: Record<string, string>;
  ltm_reported: string;
  ltm_adjusted: string;
  ltm_adjustment_total: string;
  adjustments: QoEAdjustment[];
  waterfall: WaterfallItem[];
  adjustment_count: number;
  categories_adjusted: string[];
}

export const getQoE = (dealId: string) => get<QoEReport>(`/deals/${dealId}/qoe`);

export const getAdjustmentSource = (dealId: string, adjId: string) =>
  get<{ gl_lines: unknown[]; label: string; adjustment_amount: string }>
    (`/deals/${dealId}/qoe/adjustments/${adjId}/source`);

// ─── Red Flags ────────────────────────────────────────────────────────────────

export interface RedFlag {
  flag_id: string;
  deal_id: string;
  severity: "High" | "Medium" | "Low" | "Informational";
  category: string;
  title: string;
  description: string;
  financial_impact_low: string | null;
  financial_impact_high: string | null;
  affected_periods: string[];
  source: string;
  rule_id: string | null;
  diligence_questions: string[];
  llm_context: string | null;
}

export interface RedFlagReport {
  deal_id: string;
  flags: RedFlag[];
  summary: { high: number; medium: number; low: number; informational: number; total: number };
}

export const getRedFlags = (dealId: string, severity?: string) =>
  get<RedFlagReport>(`/deals/${dealId}/redflags${severity ? `?severity=${severity}` : ""}`);

// ─── Documents ────────────────────────────────────────────────────────────────

export interface DocumentRecord {
  filename: string;
  stored_path: string;
  size_bytes: number;
  uploaded_at: string | null;
  document_type: string;
  parse_status: string;
  parse_error: string | null;
  confidence: number;
}

export interface DocumentInventory {
  deal_id: string;
  documents: DocumentRecord[];
  missing_recommended: string[];
}

export const getDocumentInventory = (dealId: string) =>
  get<DocumentInventory>(`/deals/${dealId}/documents`);

// ─── Databook ─────────────────────────────────────────────────────────────────

export async function exportDatabook(dealId: string, filename: string): Promise<void> {
  const res = await fetch(`${BASE}/deals/${dealId}/databook/export`, {
    method: "POST",
    credentials: "include",
  });
  if (!res.ok) throw new Error(`Databook export failed: ${await res.text()}`);
  const blob = await res.blob();
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  window.URL.revokeObjectURL(url);
}

// ─── Net Working Capital + Commercial Health ──────────────────────────────────

export interface NWCDataPoint {
  period: string;
  accounts_receivable: string;
  inventory: string;
  prepaid_expenses: string;
  other_current_assets: string;
  accounts_payable: string;
  accrued_liabilities: string;
  deferred_revenue: string;
  current_debt: string;
  other_current_liabilities: string;
  net_working_capital: string;
  nwc_as_pct_revenue: number | null;
}

export interface NWCPeg {
  method: "ltm_average" | "median_trailing_12" | "seasonal_adjusted";
  peg_amount: string;
  confidence_interval_low: string;
  confidence_interval_high: string;
  seasonality_detected: boolean;
  recommended: boolean;
  rationale: string;
}

export interface WorkingCapitalRatios {
  period: string;
  dso_days: number | null;
  dpo_days: number | null;
  dio_days: number | null;
  cash_conversion_cycle_days: number | null;
  ar_over_60d_pct: number | null;
  ap_over_60d_pct: number | null;
}

export interface NWCReport {
  deal_id: string;
  status: "complete" | "partial" | "skipped";
  message: string;
  has_ar_aging: boolean;
  has_ap_aging: boolean;
  data_points: NWCDataPoint[];
  pegs: NWCPeg[];
  peak_nwc: string | null;
  peak_period: string | null;
  trough_nwc: string | null;
  trough_period: string | null;
  nwc_volatility: number | null;
  ratios: WorkingCapitalRatios | null;
}

export interface CommercialHealthReport {
  deal_id: string;
  status: "complete" | "partial" | "skipped";
  message: string;
  revenue_growth_yoy_pct: Record<string, number>;
  gross_margin_trend_pct: Record<string, number>;
  ebitda_margin_trend_pct: Record<string, number>;
  revenue_volatility: number | null;
  seasonality_detected: boolean;
  seasonality_note: string | null;
  unavailable_metrics: string[];
}

export const getNWC = (dealId: string) => get<NWCReport>(`/deals/${dealId}/nwc`);
export const getCommercialHealth = (dealId: string) =>
  get<CommercialHealthReport>(`/deals/${dealId}/commercial`);

// ─── Net Debt Bridge + DCF ─────────────────────────────────────────────────────

export interface DebtBridgeComponent {
  label: string;
  amount: string;
  is_subtotal: boolean;
}

export interface NetDebtInstrumentDetail {
  instrument_id: string;
  facility_type: string;
  lender: string | null;
  principal_outstanding: string | null;
  interest_rate_pct: string | null;
  maturity_date: string | null;
  covenants_summary: string | null;
  source_document: string;
  extraction_confidence: number;
}

export interface NetDebtReport {
  deal_id: string;
  status: "complete" | "partial" | "skipped";
  message: string;
  period: string | null;
  cash_and_equivalents: string | null;
  current_debt: string | null;
  long_term_debt: string | null;
  total_debt: string | null;
  net_debt: string | null;
  net_debt_to_ebitda: number | null;
  bridge: DebtBridgeComponent[];
  instruments: NetDebtInstrumentDetail[];
  instrument_principal_total: string | null;
  reconciliation_variance: string | null;
  reconciliation_note: string | null;
}

export const getNetDebt = (dealId: string) => get<NetDebtReport>(`/deals/${dealId}/net-debt`);

export interface DCFReport {
  deal_id: string;
  status: "complete" | "skipped";
  message: string;
  projection_periods: number;
  assumptions: { discount_rate_annual: number; terminal_growth_rate_annual: number } | null;
  sum_pv_of_fcf: string | null;
  terminal_value: string | null;
  pv_of_terminal_value: string | null;
  enterprise_value: string | null;
  limitations: string[];
}

export const getDCF = (dealId: string) => get<DCFReport>(`/deals/${dealId}/dcf`);

// ─── Contracts ─────────────────────────────────────────────────────────────────

export interface DebtInstrument {
  instrument_id: string;
  facility_type: string;
  lender: string | null;
  principal_outstanding: string | null;
  interest_rate_pct: string | null;
  maturity_date: string | null;
  covenants_summary: string | null;
  change_of_control_clause: string | null;
  prepayment_terms: string | null;
  events_of_default: string | null;
  material_obligations: string[];
  source_document: string;
  extraction_confidence: number;
}

export interface ContractClause {
  clause_type: "change_of_control" | "prepayment" | "event_of_default" | "material_obligation" | "covenant";
  summary: string;
  source_document: string;
  instrument_id: string | null;
  confidence: number;
}

export interface ContractAnalysisReport {
  deal_id: string;
  status: "complete" | "partial" | "skipped";
  message: string;
  instruments: DebtInstrument[];
  clauses: ContractClause[];
}

export const getContracts = (dealId: string) => get<ContractAnalysisReport>(`/deals/${dealId}/contracts`);
export const analyzeContracts = (dealId: string) =>
  post<ContractAnalysisReport>(`/deals/${dealId}/contracts/analyze`);

// ─── Narrative ─────────────────────────────────────────────────────────────────

export interface NarrativeSection {
  section_id: "executive_summary" | "key_risks" | "qoe_highlights" | "working_capital" | "recommendations";
  title: string;
  content: string;
}

export interface NarrativeReport {
  deal_id: string;
  status: "complete" | "partial" | "skipped";
  message: string;
  generated_at: string;
  sections: NarrativeSection[];
  figures_used: Record<string, string>;
  data_gaps: string[];
}

export const getNarrative = (dealId: string) => get<NarrativeReport>(`/deals/${dealId}/narrative`);
export const generateNarrative = (dealId: string) =>
  post<NarrativeReport>(`/deals/${dealId}/narrative/generate`);

// ─── Tie-outs ──────────────────────────────────────────────────────────────────

export interface TieOutResult {
  name: string;
  expected: string;
  observed: string;
  difference: string;
  variance_pct: number;
  tolerance_pct: number;
  status: "Pass" | "Warn" | "Fail";
  source_documents: string[];
}

export interface CrossDocumentValidation {
  deal_id: string;
  tie_outs: TieOutResult[];
  warnings: string[];
}

export const getTieOuts = (dealId: string) => get<CrossDocumentValidation>(`/deals/${dealId}/tie-outs`);

// ─── Notes ─────────────────────────────────────────────────────────────────────

export interface DealNotes {
  deal_id: string;
  notes: string;
  report_draft: string[];
  updated_at: string;
}

export const getNotes = (dealId: string) => get<DealNotes>(`/deals/${dealId}/notes`);
export const saveNotes = (dealId: string, notes: string, reportDraft: string[]) =>
  put<DealNotes>(`/deals/${dealId}/notes`, { notes, report_draft: reportDraft });

// ─── Settings ──────────────────────────────────────────────────────────────────

export interface DealSettings {
  materiality_threshold: number;
  tie_out_tolerance_pct: number;
  cash_conversion_medium_pct: number;
  cash_conversion_high_pct: number;
  cash_conversion_critical_pct: number;
}

export const getDealSettings = (dealId: string) => get<DealSettings>(`/deals/${dealId}/settings`);
export const updateDealSettings = (dealId: string, updates: Partial<DealSettings>) =>
  patch<DealSettings>(`/deals/${dealId}/settings`, updates);
