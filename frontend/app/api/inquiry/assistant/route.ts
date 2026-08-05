import { z } from "zod";
import { getAnalysis, getCustomer, getDocuments, getInquiry, getRisk, getSummary } from "@/lib/mock-data/api";
import type {
  CashFlowStatement,
  CrossDocumentValidation,
  DocumentInventory,
  FinancialSummary,
  InquiryItem,
  NetDebtReport,
  NWCReport,
  QoEReport,
  RedFlagReport,
} from "@/lib/api/fdd-client";

const RequestSchema = z.object({
  question: z.string().min(2),
  deal: z.string().optional(),
  period: z.string().optional(),
  basis: z.string().optional(),
  dealId: z.string().nullable().optional(),
});

// ─── Real-deal snapshot ──────────────────────────────────────────────────────────
// Only built when a real dealId is active. Every field here traces to an actual
// backend computation — no field from the mock snapshot below (overall risk score,
// top-10 customer concentration, dashboard delta feed) has a real equivalent in this
// pipeline (no customer-level revenue is ingested, no aggregate risk score or activity
// log is computed anywhere), so those are dropped rather than approximated. See
// redflag_detector/rules.py's own "no invented numbers" note for the same principle.

const API_BASE = `${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"}/api/v1`;

async function backendGet<T>(path: string, cookie: string): Promise<T | null> {
  try {
    const res = await fetch(`${API_BASE}${path}`, { headers: { Cookie: cookie }, cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

function sumLastNPeriods(record: Record<string, string>, n: number): number {
  const keys = Object.keys(record).sort();
  return keys.slice(-n).reduce((acc, k) => acc + Number(record[k] ?? 0), 0);
}

function latestValue(record: Record<string, number | null>): number | null {
  const keys = Object.keys(record).sort();
  const last = keys[keys.length - 1];
  return last !== undefined ? record[last] : null;
}

async function buildRealSnapshot(dealId: string, cookie: string) {
  const [financials, cashFlow, qoe, redflags, tieouts, documents, inquiries, nwc, netDebt] = await Promise.all([
    backendGet<FinancialSummary>(`/deals/${dealId}/financials/summary`, cookie),
    backendGet<CashFlowStatement>(`/deals/${dealId}/financials/cash-flow`, cookie),
    backendGet<QoEReport>(`/deals/${dealId}/qoe`, cookie),
    backendGet<RedFlagReport>(`/deals/${dealId}/redflags`, cookie),
    backendGet<CrossDocumentValidation>(`/deals/${dealId}/tie-outs`, cookie),
    backendGet<DocumentInventory>(`/deals/${dealId}/documents`, cookie),
    backendGet<InquiryItem[]>(`/deals/${dealId}/inquiries`, cookie),
    backendGet<NWCReport>(`/deals/${dealId}/nwc`, cookie),
    backendGet<NetDebtReport>(`/deals/${dealId}/net-debt`, cookie),
  ]);

  const highFlags = redflags?.flags.filter((f) => f.severity === "High") ?? [];
  const mediumFlags = redflags?.flags.filter((f) => f.severity === "Medium") ?? [];
  const tieoutFails = tieouts?.tie_outs.filter((t) => t.status === "Fail") ?? [];
  const tieoutWarns = tieouts?.tie_outs.filter((t) => t.status === "Warn") ?? [];
  const blockingInquiries = (inquiries ?? []).filter(
    (i) => i.blocking && (i.status === "Open" || i.status === "In Progress")
  );

  return {
    revenueLtm: financials ? sumLastNPeriods(financials.revenue, 12) : null,
    reportedEbitdaLtm: qoe ? Number(qoe.ltm_reported) : null,
    adjustedEbitdaLtm: qoe ? Number(qoe.ltm_adjusted) : null,
    cashConversionPct: cashFlow ? latestValue(cashFlow.cash_conversion) : null,
    redFlagCounts: redflags?.summary ?? null,
    topRedFlags: (redflags?.flags ?? [])
      .filter((f) => f.severity === "High" || f.severity === "Medium")
      .slice(0, 3)
      .map((f) => `${f.title} (${f.severity})`),
    openBlockingInquiries: blockingInquiries.length,
    tieoutFailCount: tieoutFails.length,
    tieoutWarnCount: tieoutWarns.length,
    missingDocCount: documents?.missing_recommended.length ?? 0,
    qoeAdjustmentCount: qoe?.adjustment_count ?? 0,
    qoeAdjustmentTotal: qoe ? Number(qoe.ltm_adjustment_total) : null,
    nwcVolatilityPct: nwc?.nwc_volatility ?? null,
    netDebt: netDebt?.net_debt ? Number(netDebt.net_debt) : null,
    netDebtToEbitda: netDebt?.net_debt_to_ebitda ?? null,
    highFlagCount: highFlags.length,
    mediumFlagCount: mediumFlags.length,
  };
}

type RealSnapshot = Awaited<ReturnType<typeof buildRealSnapshot>>;

function fmtUsd(n: number | null): string {
  return n === null ? "N/A" : `$${(n / 1_000_000).toFixed(2)}M`;
}

function formatRealSnapshot(s: RealSnapshot): string {
  return [
    `Revenue (LTM): ${fmtUsd(s.revenueLtm)}`,
    `Reported EBITDA (LTM): ${fmtUsd(s.reportedEbitdaLtm)}`,
    `Adjusted EBITDA (LTM): ${fmtUsd(s.adjustedEbitdaLtm)}`,
    `Cash conversion (latest period): ${s.cashConversionPct === null ? "N/A" : `${(s.cashConversionPct * 100).toFixed(0)}%`}`,
    `Red flags: ${s.highFlagCount} High, ${s.mediumFlagCount} Medium`,
    `Top red flags: ${s.topRedFlags.length ? s.topRedFlags.join(", ") : "none"}`,
    `Open blocking inquiries: ${s.openBlockingInquiries}`,
    `Tie-out fails: ${s.tieoutFailCount}, warns: ${s.tieoutWarnCount}`,
    `Missing recommended documents: ${s.missingDocCount}`,
    `QoE adjustments: ${s.qoeAdjustmentCount} totalling ${fmtUsd(s.qoeAdjustmentTotal)}`,
    s.nwcVolatilityPct !== null ? `NWC volatility: ${(s.nwcVolatilityPct * 100).toFixed(0)}%` : null,
    s.netDebt !== null ? `Net debt: ${fmtUsd(s.netDebt)}${s.netDebtToEbitda !== null ? ` (${s.netDebtToEbitda.toFixed(1)}x EBITDA)` : ""}` : null,
  ]
    .filter((line): line is string => line !== null)
    .join("\n");
}

function realFallbackAnswer(question: string, s: RealSnapshot): string {
  const q = question.toLowerCase();

  if (q.includes("overall risk") || q.includes("deal risk") || q.includes("red flag")) {
    return `This deal has ${s.highFlagCount} High and ${s.mediumFlagCount} Medium red flags. ${
      s.topRedFlags.length ? `Top items: ${s.topRedFlags.join(", ")}.` : "No High/Medium flags currently open."
    }`;
  }

  if (q.includes("revenue") || q.includes("ebitda") || q.includes("cash conversion")) {
    return `Current figures: Revenue (LTM) ${fmtUsd(s.revenueLtm)}, Reported EBITDA (LTM) ${fmtUsd(s.reportedEbitdaLtm)}, Adjusted EBITDA (LTM) ${fmtUsd(s.adjustedEbitdaLtm)}, cash conversion ${s.cashConversionPct === null ? "N/A" : `${(s.cashConversionPct * 100).toFixed(0)}%`}.`;
  }

  if (q.includes("tie-out") || q.includes("tie out")) {
    return `Tie-out status: ${s.tieoutFailCount} fail and ${s.tieoutWarnCount} warn item(s).`;
  }

  if (q.includes("inquiry") || q.includes("blocking")) {
    return `There are ${s.openBlockingInquiries} open blocking inquir${s.openBlockingInquiries === 1 ? "y" : "ies"} right now.`;
  }

  if (q.includes("document") || q.includes("coverage") || q.includes("pbc")) {
    return `${s.missingDocCount} recommended document type(s) have not been uploaded yet.`;
  }

  if (q.includes("qoe") || q.includes("adjustment")) {
    return `${s.qoeAdjustmentCount} QoE adjustment(s) identified, totalling ${fmtUsd(s.qoeAdjustmentTotal)}.`;
  }

  if (q.includes("debt")) {
    return s.netDebt !== null
      ? `Net debt is ${fmtUsd(s.netDebt)}${s.netDebtToEbitda !== null ? ` (${s.netDebtToEbitda.toFixed(1)}x EBITDA)` : ""}.`
      : "Net debt has not been computed for this deal yet.";
  }

  return `From the current deal: revenue (LTM) is ${fmtUsd(s.revenueLtm)}, adjusted EBITDA (LTM) is ${fmtUsd(s.adjustedEbitdaLtm)}, ${s.highFlagCount} High red flags, and ${s.openBlockingInquiries} open blocking inquiries. Ask about revenue, red flags, tie-outs, documents, QoE adjustments, or debt for a deeper breakdown.`;
}

// ─── Mock/demo snapshot (unchanged) ───────────────────────────────────────────────
// Used only when no real dealId is active — same "seeded mock demo" fallback the
// dashboard and reports pages already preserve for that state.

function buildMockSnapshot(params: {
  summary: Awaited<ReturnType<typeof getSummary>>;
  analysis: Awaited<ReturnType<typeof getAnalysis>>;
  risk: Awaited<ReturnType<typeof getRisk>>;
  documents: Awaited<ReturnType<typeof getDocuments>>;
  customer: Awaited<ReturnType<typeof getCustomer>>;
  inquiry: Awaited<ReturnType<typeof getInquiry>>;
}) {
  const { summary, analysis, risk, documents, customer, inquiry } = params;
  const revenue = summary.metrics.find((m) => m.id === "revenue-ltm")?.value ?? "N/A";
  const reportedEbitda = summary.metrics.find((m) => m.id === "reported-ebitda")?.value ?? "N/A";
  const adjustedEbitda = summary.metrics.find((m) => m.id === "adjusted-ebitda")?.value ?? "N/A";
  const cashConversion = summary.metrics.find((m) => m.id === "cash-conv")?.value ?? "N/A";
  const overallRisk = `${risk.riskScore.toFixed(1)} / 10`;
  const top10Concentration = customer.metrics.find((m) => m.id === "cust-top10")?.value ?? "N/A";
  const openBlockingInquiries = inquiry.inquiries.filter((i) => i.blocking && i.status !== "Closed").length;
  const tieoutFails = risk.tieOuts.filter((t) => t.status === "Fail").length;
  const tieoutWarns = risk.tieOuts.filter((t) => t.status === "Warn").length;
  const missingDocs = documents.coverage.reduce((acc, row) => acc + row.months.filter((m) => m.status === "Missing").length, 0);

  return {
    revenue,
    reportedEbitda,
    adjustedEbitda,
    cashConversion,
    overallRisk,
    top10Concentration,
    openBlockingInquiries,
    tieoutFails,
    tieoutWarns,
    missingDocs,
    riskHotspots: [...risk.dimensions].sort((a, b) => b.score - a.score).slice(0, 3),
    recentChanges: summary.deltaFeed.slice(0, 4).map((d) => `${d.type}: ${d.message}`),
    highRiskAddbacks: analysis.qoeMetrics.find((m) => m.id === "qoe-highrisk")?.value ?? "N/A",
  };
}

function formatMockSnapshot(snapshot: ReturnType<typeof buildMockSnapshot>) {
  return [
    `Revenue (LTM): ${snapshot.revenue}`,
    `Reported EBITDA (LTM): ${snapshot.reportedEbitda}`,
    `Adjusted EBITDA (LTM): ${snapshot.adjustedEbitda}`,
    `Cash conversion: ${snapshot.cashConversion}`,
    `Overall deal risk: ${snapshot.overallRisk}`,
    `Top 10 concentration: ${snapshot.top10Concentration}`,
    `Open blocking inquiries: ${snapshot.openBlockingInquiries}`,
    `Tie-out fails: ${snapshot.tieoutFails}`,
    `Tie-out warns: ${snapshot.tieoutWarns}`,
    `Missing document cells in coverage heatmap: ${snapshot.missingDocs}`,
    `High-risk addbacks count: ${snapshot.highRiskAddbacks}`,
    `Risk hotspots: ${snapshot.riskHotspots.map((r) => `${r.subject} (${r.score.toFixed(1)})`).join(", ")}`,
    `Recent changes: ${snapshot.recentChanges.join(" | ")}`,
  ].join("\n");
}

function mockFallbackAnswer(question: string, snapshot: ReturnType<typeof buildMockSnapshot>) {
  const q = question.toLowerCase();

  if (q.includes("overall risk") || q.includes("deal risk")) {
    return `Overall deal risk is ${snapshot.overallRisk}. Top hotspots are ${snapshot.riskHotspots.map((r) => `${r.subject} (${r.score.toFixed(1)})`).join(", ")}.`;
  }

  if (q.includes("revenue") || q.includes("ebitda") || q.includes("cash conversion")) {
    return `Current dashboard metrics: Revenue (LTM) ${snapshot.revenue}, Reported EBITDA (LTM) ${snapshot.reportedEbitda}, Adjusted EBITDA (LTM) ${snapshot.adjustedEbitda}, Cash conversion ${snapshot.cashConversion}.`;
  }

  if (q.includes("tie-out") || q.includes("tie out")) {
    return `Tie-out status: ${snapshot.tieoutFails} fail and ${snapshot.tieoutWarns} warn items. Highest-risk check remains TB <-> BS (A=L+E) as shown in the risk table.`;
  }

  if (q.includes("inquiry") || q.includes("blocking")) {
    return `There are ${snapshot.openBlockingInquiries} open blocking inquiries right now. Prioritize AP aging reconciliation and FX adjustment support.`;
  }

  if (q.includes("document") || q.includes("coverage") || q.includes("pbc")) {
    return `Document coverage has ${snapshot.missingDocs} missing cells in the heatmap. Open PBC items include AP aging vendor detail, FX adjustment support, and bank rec support.`;
  }

  return `From the current dashboard: overall deal risk is ${snapshot.overallRisk}, revenue is ${snapshot.revenue}, adjusted EBITDA is ${snapshot.adjustedEbitda}, cash conversion is ${snapshot.cashConversion}, and top-10 concentration is ${snapshot.top10Concentration}. Ask about revenue, risk, tie-outs, documents, or inquiries for a deeper breakdown.`;
}

// ─── Shared: Anthropic call + route handler ───────────────────────────────────────

async function callAnthropic(question: string, snapshotText: string) {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) return null;

  const model = process.env.ANTHROPIC_MODEL ?? "claude-3-5-sonnet-latest";
  const response = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": apiKey,
      "anthropic-version": "2023-06-01",
    },
    body: JSON.stringify({
      model,
      temperature: 0.2,
      max_tokens: 1024,
      system: "You are TAM Inquiry Copilot for financial due diligence. Answer clearly, use only provided dashboard context, do not invent data, and keep the answer concise and actionable.",
      messages: [
        {
          role: "user",
          content: `Dashboard context:\n${snapshotText}\n\nUser question: ${question}`,
        },
      ],
    }),
  });

  if (!response.ok) {
    throw new Error(`Anthropic API error: ${response.status}`);
  }

  const json = (await response.json()) as {
    content?: Array<{ type?: string; text?: string }>;
  };

  const text = json.content
    ?.filter((c) => c.type === "text")
    .map((c) => c.text ?? "")
    .join("\n")
    .trim();

  if (text) {
    return { answer: text, model };
  }

  return { answer: "I could not generate a response from the model output.", model };
}

export async function POST(request: Request) {
  try {
    const body = RequestSchema.parse(await request.json());

    let snapshotText: string;
    let fallback: string;

    if (body.dealId) {
      const cookie = request.headers.get("cookie") ?? "";
      const snapshot = await buildRealSnapshot(body.dealId, cookie);
      snapshotText = formatRealSnapshot(snapshot);
      fallback = realFallbackAnswer(body.question, snapshot);
    } else {
      const [summary, analysis, risk, documents, customer, inquiry] = await Promise.all([
        getSummary(body.period ?? null, body.basis ?? null, body.deal ?? null, { withDelay: false }),
        getAnalysis(body.period ?? null, body.basis ?? null, body.deal ?? null, { withDelay: false }),
        getRisk(body.deal ?? null, body.period ?? null, body.basis ?? null, { withDelay: false }),
        getDocuments(body.deal ?? null, { withDelay: false }),
        getCustomer(body.period ?? null, body.basis ?? null, body.deal ?? null, { withDelay: false }),
        getInquiry(body.deal ?? null, body.period ?? null, body.basis ?? null, { withDelay: false }),
      ]);
      const snapshot = buildMockSnapshot({ summary, analysis, risk, documents, customer, inquiry });
      snapshotText = formatMockSnapshot(snapshot);
      fallback = mockFallbackAnswer(body.question, snapshot);
    }

    try {
      const llm = await callAnthropic(body.question, snapshotText);
      if (llm) {
        return Response.json({
          answer: llm.answer,
          mode: "llm",
          model: llm.model,
        });
      }
    } catch {
      // fall through to deterministic answer
    }

    return Response.json({
      answer: fallback,
      mode: "fallback",
      model: "dashboard-rules-v1",
    });
  } catch {
    return Response.json({
      answer: "I could not process that request. Please try again with a clearer question.",
      mode: "fallback",
      model: "dashboard-rules-v1",
    });
  }
}
