/**
 * FDD Engine API client — wraps all calls to the FastAPI backend.
 * Base URL: http://localhost:8000/api/v1
 *
 * All amounts come back as strings (Decimal) and are parsed to number here
 * only for display. Arithmetic on financial figures must use the raw string
 * values or the backend.
 */

const BASE = "http://localhost:8000/api/v1";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
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
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`POST ${path} → ${res.status}: ${text}`);
  }
  return res.json();
}

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
  const res = await fetch(`${BASE}/deals/${dealId}/upload`, { method: "POST", body: form });
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
  const res = await fetch(`${BASE}/deals/${dealId}/databook/export`, { method: "POST" });
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
