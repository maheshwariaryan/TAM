"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ChartCard } from "@/components/charts/chart-card";
import { RiskZoneMapChart } from "@/components/charts/common-charts";
import { DataTable } from "@/components/tables/data-table";
import { useApiQuery } from "@/hooks/use-api-query";
import { RiskResponseSchema, RiskRegisterRowSchema } from "@/lib/schemas/types";
import { z } from "zod";
import { SeverityBadge } from "@/components/severity-badge";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { formatCurrency, formatPct } from "@/lib/utils/format";
import type { Severity } from "@/lib/schemas/types";
import { useGlobalStore } from "@/lib/store/use-global-store";
import { RedFlagCenter } from "@/components/fdd/redflag-center";

export default function RiskAssessmentPage() {
  return (
    <Suspense fallback={<div className="h-80 animate-pulse rounded-lg bg-muted" />}>
      <RiskAssessmentPageContent />
    </Suspense>
  );
}

function RiskAssessmentPageContent() {
  const router = useRouter();
  const params = useSearchParams();
  const { deal, dealId, period, basis } = useGlobalStore();
  const query = useApiQuery(
    ["risk", deal, period, basis],
    `/api/deal/risk?deal=${encodeURIComponent(deal)}&period=${encodeURIComponent(period)}&basis=${encodeURIComponent(basis)}`,
    RiskResponseSchema
  );
  const [selectedRisk, setSelectedRisk] = useState<z.infer<typeof RiskRegisterRowSchema> | null>(null);
  const [highlightedTieOutId, setHighlightedTieOutId] = useState<string | null>(null);
  const data = query.data;
  const focusedTieOutName = params.get("focus") === "tieout" ? params.get("name") : null;
  const makeTieOutRowId = (name: string) => `tie-${name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
  const tieOutRows = useMemo(
    () => (data?.tieOuts ?? []).map((row) => ({ ...row, id: makeTieOutRowId(row.name) })),
    [data?.tieOuts]
  );

  useEffect(() => {
    if (!focusedTieOutName || !data) return;
    const target = data.tieOuts.find((row) => row.name.toLowerCase() === focusedTieOutName.toLowerCase());
    if (!target) return;
    const rowId = makeTieOutRowId(target.name);
    setHighlightedTieOutId(rowId);

    const scrollTimer = window.setTimeout(() => {
      const node = document.querySelector(`[data-rowid="${rowId}"]`);
      if (node instanceof HTMLElement) {
        node.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }, 180);

    const clearTimer = window.setTimeout(() => setHighlightedTieOutId(null), 2200);
    return () => {
      window.clearTimeout(scrollTimer);
      window.clearTimeout(clearTimer);
    };
  }, [data, focusedTieOutName]);

  if (query.isLoading || !data) return <div className="h-80 animate-pulse rounded-lg bg-muted" />;
  const overallSeverity: Severity = data.riskScore >= 7 ? "Red" : data.riskScore >= 4.5 ? "Amber" : "Green";
  const redCount = data.register.filter((r) => r.severity === "Red").length;
  const amberCount = data.register.filter((r) => r.severity === "Amber").length;
  const greenCount = data.register.filter((r) => r.severity === "Green").length;
  const openRiskCount = data.register.filter((r) => r.status !== "Mitigated").length;
  const resolvedRiskCount = data.register.filter((r) => r.status === "Mitigated").length;
  const topRisks = [...data.dimensions].sort((a, b) => b.score - a.score).slice(0, 3);
  const gaugeFillPct = Math.max(0, Math.min(100, (data.riskScore / 10) * 100));
  const registerWithProbability = data.register.map((row, idx) => ({
    ...row,
    probability: row.severity === "Red" ? "High" : row.severity === "Amber" ? "Medium" : "Low",
    adjustmentReliancePct: row.id === "R-01" ? 5.4 : row.id === "R-02" ? 2.8 : row.id === "R-03" ? 1.7 : 0.8,
    openResolved: row.status === "Mitigated" ? "Resolved" : "Open",
    riskCategory:
      idx === 0
        ? "Earnings Sustainability Risk"
        : idx === 1
          ? "Revenue Concentration Risk"
          : idx === 2
            ? "Working Capital Risk"
            : "Data Quality Risk",
  }));
  const anomalyRows = [
    {
      metric: "Discount rate variance (%)",
      current: `${(Math.max(3.2, data.riskScore + 0.6)).toFixed(1)}%`,
      prior: `${(Math.max(2.2, data.riskScore - 1.1)).toFixed(1)}%`,
      variance: `+${(1.7).toFixed(1)}ppt`,
      status: data.riskScore >= 5.5 ? "Warn" : "Pass",
    },
    {
      metric: "Margin outliers by product/customer",
      current: `${Math.max(1, Math.round(data.dimensions[3]?.score / 2))} outliers`,
      prior: `${Math.max(1, Math.round((data.dimensions[3]?.score ?? 4) / 3))} outlier`,
      variance: `+${Math.max(0, Math.round((data.dimensions[3]?.score ?? 4) / 2) - 1)}`,
      status: (data.dimensions[3]?.score ?? 4) >= 6 ? "Warn" : "Pass",
    },
    {
      metric: "Payroll spikes (% change)",
      current: `+${(6 + (data.dimensions[4]?.score ?? 5)).toFixed(1)}%`,
      prior: `+${(3.5 + (data.dimensions[4]?.score ?? 5) / 2).toFixed(1)}%`,
      variance: `+${(2.5 + (data.dimensions[4]?.score ?? 5) / 2).toFixed(1)}ppt`,
      status: (data.dimensions[4]?.score ?? 5) >= 6 ? "Warn" : "Pass",
    },
    {
      metric: "Refunds / credits as % of revenue",
      current: `${(1.4 + (data.dimensions[2]?.score ?? 5) / 3).toFixed(1)}%`,
      prior: `${(1.1 + (data.dimensions[2]?.score ?? 5) / 4).toFixed(1)}%`,
      variance: `+${(0.4 + (data.dimensions[2]?.score ?? 5) / 10).toFixed(1)}ppt`,
      status: (data.dimensions[2]?.score ?? 5) >= 7 ? "Warn" : "Pass",
    },
    {
      metric: "Manual journal entry volume (%)",
      current: `${(6.4 + (data.dimensions[0]?.score ?? 5) / 2).toFixed(1)}%`,
      prior: `${(5.1 + (data.dimensions[0]?.score ?? 5) / 3).toFixed(1)}%`,
      variance: `+${(1.2 + (data.dimensions[0]?.score ?? 5) / 8).toFixed(1)}ppt`,
      status: (data.dimensions[0]?.score ?? 5) >= 6 ? "Warn" : "Pass",
    },
  ];

  return (
    <div className="space-y-5">
      {/* ── Real Red Flag Command Center (FDD backend) ── */}
      {dealId ? (
        <div>
          <h2 className="mb-4 text-xl font-semibold">Red Flag Command Center</h2>
          <RedFlagCenter dealId={dealId} />
        </div>
      ) : (
        <Card>
          <CardContent className="py-6 text-center text-sm text-muted-foreground">
            No deal selected. Upload data via <strong>Upload Deal Data</strong> first.
          </CardContent>
        </Card>
      )}

      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">Risk Assessment</h2>
        <p className="rounded-full bg-muted px-3 py-1 text-sm">Overall deal risk: {data.riskScore}/10</p>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-1">
          <CardHeader><CardTitle>Overall Deal Risk Indicator</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-center gap-4">
              <div
                className="grid h-24 w-24 shrink-0 place-items-center rounded-full"
                style={{
                  aspectRatio: "1 / 1",
                  background: `conic-gradient(#f97316 ${gaugeFillPct}%, #e2e8f0 ${gaugeFillPct}% 100%)`,
                }}
              >
                <div className="grid h-16 w-16 shrink-0 place-items-center rounded-full bg-card text-lg font-bold" style={{ aspectRatio: "1 / 1" }}>
                  {data.riskScore.toFixed(1)}
                </div>
              </div>
              <div className="space-y-2">
                <SeverityBadge severity={overallSeverity} />
                <p className="text-sm text-muted-foreground">Weighted score from tie-outs, anomalies, and evidence quality.</p>
              </div>
            </div>
            <div className="grid grid-cols-3 gap-2 text-center text-xs">
              <div className="rounded bg-rose-100 p-2 text-rose-800 dark:bg-rose-500/20 dark:text-rose-200"><p className="font-semibold">{redCount}</p><p>Red</p></div>
              <div className="rounded bg-amber-100 p-2 text-amber-800 dark:bg-amber-500/20 dark:text-amber-200"><p className="font-semibold">{amberCount}</p><p>Amber</p></div>
              <div className="rounded bg-emerald-100 p-2 text-emerald-800 dark:bg-emerald-500/20 dark:text-emerald-200"><p className="font-semibold">{greenCount}</p><p>Green</p></div>
            </div>
            <div className="grid grid-cols-2 gap-2 text-center text-xs">
              <div className="rounded border bg-card p-2"><p className="font-semibold">{openRiskCount}</p><p>Open Risks</p></div>
              <div className="rounded border bg-card p-2"><p className="font-semibold">{resolvedRiskCount}</p><p>Resolved Risks</p></div>
            </div>
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader><CardTitle>Risk Hotspots</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            {topRisks.map((risk) => (
              <div key={risk.subject} className="rounded border bg-card p-3">
                <div className="mb-1 flex items-center justify-between text-sm">
                  <span className="font-medium">{risk.subject}</span>
                  <span className="font-semibold">{risk.score.toFixed(1)} / 10</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-muted">
                  <div
                    className={`h-full ${risk.score >= 7 ? "bg-rose-500" : risk.score >= 4.5 ? "bg-amber-500" : "bg-emerald-500"}`}
                    style={{ width: `${(risk.score / 10) * 100}%` }}
                  />
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      <ChartCard title="Risk Zone Map (where risk lives)" steps={[{ title: "Inputs", description: "Tie-out, variance, and anomaly signals", references: ["Tie-out engine", "Anomaly monitor"] }, { title: "Transformations", description: "Weighted component scoring plus zone bucketing (Low/Watch/High)", references: ["Risk weighting matrix"] }, { title: "Formula", description: "Weighted average score (0-10) and zone segmentation by thresholds 4.5 and 7.0", references: ["Risk model v3"] }, { title: "Filters / Overrides", description: "Analyst override requires memo", references: ["Override control"] }]} renderChart={(expanded) => <RiskZoneMapChart data={data.dimensions} expanded={expanded} />} />

      <DataTable
        title="Tie-out scoreboard"
        rows={tieOutRows}
        rowClassName={(row) => (highlightedTieOutId && row.id === highlightedTieOutId ? "tam-source-highlight" : "")}
        columns={[
          { key: "name", header: "Check" },
          { key: "expected", header: "Expected", render: (r) => formatCurrency(r.expected) },
          { key: "observed", header: "Observed", render: (r) => formatCurrency(r.observed) },
          { key: "diff", header: "Diff", render: (r) => formatCurrency(r.diff) },
          { key: "variancePct", header: "%", render: (r) => formatPct(r.variancePct) },
          { key: "tolerancePct", header: "Tolerance", render: (r) => formatPct(r.tolerancePct) },
          {
            key: "status",
            header: "Status",
            render: (r) => (
              <span className={`rounded-full px-2 py-1 text-xs font-semibold ${r.status === "Pass" ? "bg-emerald-100 text-emerald-700" : r.status === "Warn" ? "bg-amber-100 text-amber-700" : "bg-rose-100 text-rose-700"}`}>
                {r.status}
              </span>
            ),
          },
        ]}
      />

      <DataTable
        title="Risk register"
        rows={registerWithProbability}
        onRowClick={(row) => setSelectedRisk(row)}
        columns={[
          { key: "risk", header: "Risk" },
          { key: "riskCategory", header: "Category" },
          { key: "severity", header: "Severity", render: (r) => <SeverityBadge severity={r.severity} /> },
          { key: "probability", header: "Probability" },
          { key: "adjustmentReliancePct", header: "Adjustment reliance (% EBITDA)", render: (r) => `${r.adjustmentReliancePct.toFixed(1)}%` },
          { key: "impactArea", header: "Impact Area" },
          { key: "exposureRange", header: "Exposure Range" },
          { key: "openResolved", header: "Open/Resolved" },
          { key: "evidence", header: "Evidence" },
        ]}
      />

      <DataTable
        title="Anomaly Detection Monitor"
        rows={anomalyRows}
        columns={[
          { key: "metric", header: "Metric" },
          { key: "current", header: "Current" },
          { key: "prior", header: "Prior" },
          { key: "variance", header: "Variance" },
          {
            key: "status",
            header: "Status",
            render: (r) => (
              <span className={`rounded-full px-2 py-1 text-xs font-semibold ${r.status === "Pass" ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"}`}>
                {r.status}
              </span>
            ),
          },
        ]}
      />

      <Sheet open={!!selectedRisk} onOpenChange={(v) => !v && setSelectedRisk(null)}>
        <SheetContent side="right" className="w-[440px]">
          {selectedRisk ? (
            <div className="space-y-3">
              <h3 className="text-lg font-semibold">{selectedRisk.risk}</h3>
              <SeverityBadge severity={selectedRisk.severity} />
              <p className="text-sm"><span className="font-semibold">Impact area:</span> {selectedRisk.impactArea}</p>
              <p className="text-sm"><span className="font-semibold">Exposure:</span> {selectedRisk.exposureRange}</p>
              <p className="text-sm"><span className="font-semibold">Evidence:</span> {selectedRisk.evidence}</p>
              <Button variant="outline" onClick={() => router.push(`/inquiry?prefill=${encodeURIComponent(selectedRisk.risk)}`)}>Create inquiry</Button>
            </div>
          ) : null}
        </SheetContent>
      </Sheet>
    </div>
  );
}
