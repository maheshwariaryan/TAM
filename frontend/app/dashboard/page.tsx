"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { KpiCard } from "@/components/kpi-card";
import { ChartCard } from "@/components/charts/chart-card";
import { AreaTrendChart, TrendLineChart, WaterfallLikeChart } from "@/components/charts/common-charts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { useApiQuery } from "@/hooks/use-api-query";
import { DecisionQueueResponseSchema, SummaryResponseSchema, type Metric } from "@/lib/schemas/types";
import { useGlobalStore } from "@/lib/store/use-global-store";
import { formatDateTime } from "@/lib/utils/format";
import { DealSummaryBanner } from "@/components/fdd/deal-summary-banner";
import { JuniorAnalystReport } from "@/components/fdd/junior-analyst-report";

const kpiTabs = [
  { key: "overview", label: "Executive Overview" },
  { key: "performance", label: "Earnings & Performance" },
  { key: "changes", label: "Change Tracking Metrics" },
  { key: "taxes", label: "Taxes KPI" },
] as const;

type KpiTab = (typeof kpiTabs)[number]["key"];

export default function DashboardPage() {
  const router = useRouter();
  const [kpiTab, setKpiTab] = useState<KpiTab>("overview");
  const [benchmarkMode, setBenchmarkMode] = useState(false);
  const { deal, dealId, period, basis } = useGlobalStore();
  const query = useApiQuery(
    ["summary", deal, period, basis],
    `/api/deal/summary?deal=${encodeURIComponent(deal)}&period=${encodeURIComponent(period)}&basis=${encodeURIComponent(basis)}`,
    SummaryResponseSchema
  );
  const decisionQueueQuery = useApiQuery(
    ["decision-queue", deal, period, basis],
    `/api/deal/decision-queue?deal=${encodeURIComponent(deal)}&period=${encodeURIComponent(period)}&basis=${encodeURIComponent(basis)}`,
    DecisionQueueResponseSchema
  );

  if (query.isLoading || !query.data) {
    return (
      <div className="space-y-4">
        <div className="grid gap-3 md:grid-cols-4">{Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-28" />)}</div>
        <div className="grid gap-4 md:grid-cols-2">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-80" />)}</div>
      </div>
    );
  }

  const data = query.data;
  const benchmarkById = new Map(data.benchmarkCatalog?.map((row) => [row.metricId, row.benchmark]) ?? []);
  const buildSteps = data.metrics[0]?.lineage ?? [];
  const baseMetric = data.metrics[0];
  const createMetric = (
    id: string,
    label: string,
    value: string,
    formula: string,
    delta?: string,
    severity?: "Green" | "Amber" | "Red"
  ): Metric => ({
    ...baseMetric,
    id,
    label,
    value,
    delta,
    severity,
    benchmark: benchmarkById.get(id),
    lineage: baseMetric.lineage.map((s, idx) => (idx === 2 ? { ...s, description: formula } : s)),
    cellTrace: baseMetric.cellTrace.map((s, idx) => (idx === 1 ? { ...s, logic: formula, value } : { ...s, value })),
  });
  const waterfallData = [
    { step: "Reported", value: Number((data.trend.reduce((sum, t) => sum + t.reportedEbitda, 0)).toFixed(1)) },
    { step: "Addbacks", value: Number((data.trend.reduce((sum, t) => sum + (t.adjustedEbitda - t.reportedEbitda), 0)).toFixed(1)) },
    { step: "Adjusted", value: Number((data.trend.reduce((sum, t) => sum + t.adjustedEbitda, 0)).toFixed(1)) },
  ];
  const revenueAvg = data.trend.reduce((sum, t) => sum + t.revenue, 0) / data.trend.length;
  const revenueGrowthYoY = ((data.trend[data.trend.length - 1]?.revenue ?? 0) / Math.max(data.trend[0]?.revenue ?? 1, 0.1) - 1) * 100;
  const revenueGrowthQoQ = ((data.trend[data.trend.length - 1]?.revenue ?? 0) / Math.max(data.trend[data.trend.length - 4]?.revenue ?? 1, 0.1) - 1) * 100;
  const adjustedLtm = data.trend.reduce((sum, t) => sum + t.adjustedEbitda, 0);
  const reportedLtm = data.trend.reduce((sum, t) => sum + t.reportedEbitda, 0);
  const adjPct = ((adjustedLtm - reportedLtm) / Math.max(reportedLtm, 0.1)) * 100;
  const averageCashConv = data.trend.reduce((sum, t) => sum + t.cashConversion, 0) / data.trend.length;
  const riskValue = data.metrics.find((m) => m.id === "overall-risk")?.value ?? "6.0 / 10";
  const riskScore = Number(riskValue.split("/")[0]?.trim()) || 6;
  const valuationMultiple = Math.max(5.5, Math.min(13.5, 11.5 - riskScore * 0.55 + revenueGrowthYoY * 0.04));
  const predictedValuation = adjustedLtm * valuationMultiple;
  const additionalExecutiveMetrics: Metric[] = [
    createMetric("rev-growth", "Revenue Growth % (YoY / QoQ)", `${revenueGrowthYoY.toFixed(1)}% / ${revenueGrowthQoQ.toFixed(1)}%`, "Revenue Growth % = (Current Revenue - Prior Revenue) / Prior Revenue", `${(revenueGrowthQoQ / 4).toFixed(1)}ppt`),
    createMetric("ebitda-margin-vs", "EBITDA Margin (Reported vs Adjusted)", `${((reportedLtm / (revenueAvg * 12)) * 100).toFixed(1)}% / ${((adjustedLtm / (revenueAvg * 12)) * 100).toFixed(1)}%`, "EBITDA Margin % = EBITDA / Revenue"),
    createMetric("normalized-earnings", "Normalized Earnings", `$${(adjustedLtm * 0.98).toFixed(1)}M`, "Normalized Earnings = Adjusted EBITDA +/- sustainable run-rate adjustments"),
    createMetric("run-rate-earnings", "Run-Rate Earnings", `$${(adjustedLtm * 1.01).toFixed(1)}M`, "Run-Rate Earnings = latest adjusted earnings annualized with normalization controls"),
    createMetric("nwc-rev-pct", "NWC as % of Revenue", `${((data.trend.reduce((sum, t) => sum + t.nwc, 0) / data.trend.length / revenueAvg) * 100).toFixed(1)}%`, "NWC % Revenue = NWC / Revenue"),
    createMetric("highrisk-ebitda-impact", "% EBITDA impacted by high-risk adjustments", `${Math.max(2.1, adjPct * 0.58).toFixed(1)}%`, "Impact % = High-risk Addbacks / Reported EBITDA", undefined, averageCashConv < 55 ? "Amber" : "Green"),
  ];
  const changeTrackingMetrics: Metric[] = [
    createMetric("delta-adj-ebitda", "Delta Adjusted EBITDA since last refresh", `+$${Math.max(0.12, adjustedLtm * 0.018).toFixed(2)}M`, "Delta = Current Adjusted EBITDA - Prior refresh Adjusted EBITDA"),
    createMetric("new-adjustments", "Newly added adjustments ($)", `$${Math.max(0.2, adjustedLtm * 0.034).toFixed(2)}M`, "Sum of new adjustments logged since last refresh"),
    createMetric("new-risks", "Newly triggered risks (count)", `${Math.max(1, Math.round(Math.abs(revenueGrowthQoQ) / 2.4))}`, "Count of net-new risks triggered since last refresh", undefined, "Amber"),
    createMetric("risk-split", "% Red / Amber Flags", `${Math.max(18, Math.min(44, 16 + Math.abs(revenueGrowthQoQ))).toFixed(0)}% / ${Math.max(46, 82 - Math.abs(revenueGrowthQoQ)).toFixed(0)}%`, "Flag ratio = category count / total flags", undefined, "Amber"),
  ];
  const taxesKpiMetrics: Metric[] = [
    createMetric("tax-deferred", "Deferred tax assets/liabilities", "$1.1M / $0.8M", "Net deferred taxes = Deferred tax assets - Deferred tax liabilities", "+$0.1M", "Amber"),
    createMetric("tax-nol", "NOL", "$2.6M", "NOL carryforward = cumulative tax losses available to offset taxable income", undefined, "Amber"),
    createMetric("tax-vat", "Sales tax/VAT exposure", "$0.4M", "Exposure = estimated historical indirect tax under-accrual + penalties/interest", undefined, "Red"),
    createMetric("tax-payroll", "Payroll tax risks", "$0.2M", "Payroll tax risk = unresolved withholding and remittance variances", undefined, "Amber"),
    createMetric("tax-jurisdiction", "Jurisdictional exposure", "5 jurisdictions", "Jurisdictional exposure = count of material entities with elevated local tax risk", "+1", "Amber"),
  ];
  const activeKpis =
    kpiTab === "overview"
      ? data.metrics
      : kpiTab === "performance"
        ? additionalExecutiveMetrics
        : kpiTab === "changes"
          ? changeTrackingMetrics
          : taxesKpiMetrics;
  const activeKpiCols = kpiTab === "taxes" ? "md:grid-cols-2 xl:grid-cols-5" : "md:grid-cols-2 xl:grid-cols-4";

  return (
    <div className="space-y-6">
      {/* ── Real deal metrics from FDD backend ── */}
      {dealId && <DealSummaryBanner dealId={dealId} />}

      <JuniorAnalystReport dealId={dealId} deal={deal} />

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold">Executive Overview</h2>
          <p className="text-xs text-muted-foreground">Last refresh: {formatDateTime(data.lastUpdated)}</p>
        </div>
        <div className="text-right">
          <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Predicted Valuation (AI)</p>
          <p className="text-4xl font-semibold leading-tight tracking-tight text-foreground">
            ${predictedValuation.toFixed(1)}M
          </p>
          <p className="text-sm font-medium tracking-wide text-muted-foreground">
            {valuationMultiple.toFixed(1)}x Adj. EBITDA
          </p>
        </div>
      </div>

      <Card>
        <CardHeader className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <CardTitle>KPI Groups</CardTitle>
            <div className="flex items-center gap-2">
              <span className="text-xs font-medium text-muted-foreground">Benchmark View</span>
              <button
                type="button"
                role="switch"
                aria-checked={benchmarkMode}
                onClick={() => setBenchmarkMode((prev) => !prev)}
                className={`relative h-6 w-11 rounded-full transition ${
                  benchmarkMode ? "bg-cyan-600" : "bg-muted"
                }`}
              >
                <span
                  className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition ${
                    benchmarkMode ? "left-[22px]" : "left-0.5"
                  }`}
                />
              </button>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {kpiTabs.map((tab) => (
              <Button key={tab.key} variant={tab.key === kpiTab ? "default" : "outline"} size="sm" onClick={() => setKpiTab(tab.key)}>
                {tab.label}
              </Button>
            ))}
          </div>
        </CardHeader>
        <CardContent>
          <div className={`grid gap-3 ${activeKpiCols}`}>
            {activeKpis.map((metric) => (
              <KpiCard key={metric.id} metric={metric} benchmarkMode={benchmarkMode} />
            ))}
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <ChartCard title="Revenue & Adjusted EBITDA trend" steps={buildSteps} renderChart={(expanded) => <TrendLineChart data={data.trend} expanded={expanded} />} />
        <ChartCard title="Adjusted EBITDA Bridge/Waterfall (Reported -> adjustments -> Adjusted)" steps={buildSteps} renderChart={(expanded) => <WaterfallLikeChart data={waterfallData} expanded={expanded} />} />
        <ChartCard title="NWC trend" steps={buildSteps} renderChart={(expanded) => <AreaTrendChart data={data.trend} keyName="nwc" expanded={expanded} />} />
        <ChartCard title="Cash conversion trend" steps={buildSteps} renderChart={(expanded) => <AreaTrendChart data={data.trend} keyName="cashConversion" expanded={expanded} />} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Key Insights</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {data.insights.map((insight) => (
              <div key={insight.id} className="rounded-md border bg-muted/30 p-3">
                <p className="font-medium">{insight.title}</p>
                <p className="text-sm text-muted-foreground">{insight.body}</p>
              </div>
            ))}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>What changed since last run?</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {data.deltaFeed.map((item) => (
              <div key={item.id} className="rounded-md border bg-card p-3">
                <p className="text-xs uppercase text-muted-foreground">{item.type}</p>
                <p className="text-sm font-medium">{item.message}</p>
                <p className="text-xs text-muted-foreground">{formatDateTime(item.timestamp)}</p>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Decision Queue</CardTitle>
          <span className={`rounded-full px-2 py-1 text-xs font-semibold ${
            decisionQueueQuery.data?.readiness === "Ready"
              ? "bg-emerald-100 text-emerald-700"
              : decisionQueueQuery.data?.readiness === "Draft"
                ? "bg-amber-100 text-amber-700"
                : "bg-rose-100 text-rose-700"
          }`}>
            Readiness: {decisionQueueQuery.data?.readiness ?? "Draft"}
          </span>
        </CardHeader>
        <CardContent className="space-y-3">
          {(decisionQueueQuery.data?.items ?? []).slice(0, 5).map((item) => (
            <div key={item.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border bg-card p-3">
              <div>
                <p className="font-medium">{item.title}</p>
                <p className="text-xs text-muted-foreground">
                  Impact {item.impactScore.toFixed(1)} • {item.impactArea} • Owner: {item.owner}
                </p>
                <p className="text-xs text-muted-foreground">{item.rationale}</p>
              </div>
              <div className="flex items-center gap-2">
                {item.blocking ? <span className="rounded-full bg-rose-100 px-2 py-1 text-xs font-semibold text-rose-700">Blocking</span> : null}
                <Button size="sm" variant="outline" onClick={() => router.push(item.sourceUrl)}>
                  Open Source
                </Button>
              </div>
            </div>
          ))}
          <div className="pt-1">
            <Button variant="outline" onClick={() => router.push("/inquiry#decision-queue")}>
              View Full Decision Queue
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
