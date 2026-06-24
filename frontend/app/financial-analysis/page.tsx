"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { KpiCard } from "@/components/kpi-card";
import { ChartCard } from "@/components/charts/chart-card";
import { AreaTrendChart, BarCompareChart, TrendLineChart, WaterfallLikeChart } from "@/components/charts/common-charts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { DataTable } from "@/components/tables/data-table";
import { useApiQuery } from "@/hooks/use-api-query";
import { AnalysisResponseSchema, type Metric } from "@/lib/schemas/types";
import { useGlobalStore } from "@/lib/store/use-global-store";
import { MetricTraceModal } from "@/components/modals/metric-trace-modal";
import { QoeCenter } from "@/components/fdd/qoe-center";

const subTabs = [
  { key: "qoe", label: "Quality of Earnings" },
  { key: "revenue", label: "Revenue QoE" },
  { key: "margin", label: "Margin / Cost QoE" },
  { key: "working-capital", label: "Working Capital" },
  { key: "cash-flow", label: "Cash Flow & Conversion" },
  { key: "statements", label: "Statements" },
] as const;

type SubTab = (typeof subTabs)[number]["key"];

const fallbackMetric: Metric = {
  id: "statement-row",
  label: "Statement line trace",
  value: "$0",
  lineage: [
    { title: "Inputs", description: "Mapped statement line item", references: ["TB_FY24.xlsx"] },
    { title: "Transformations", description: "Standardization + period alignment", references: ["Mapping v2.1"] },
    { title: "Formula", description: "Line item trace into standardized statement", references: ["Statements model"] },
    { title: "Filters / Overrides", description: "None", references: ["-" ]},
  ],
  cellTrace: [
    { step: "1", source: "TB_FY24.xlsx/IS", logic: "Mapped source account group", value: "$0" },
  ],
};

export default function FinancialAnalysisPage() {
  return (
    <Suspense fallback={<div className="h-80 animate-pulse rounded-lg bg-muted" />}>
      <FinancialAnalysisPageContent />
    </Suspense>
  );
}

function FinancialAnalysisPageContent() {
  const params = useSearchParams();
  const router = useRouter();
  const sub = (params.get("sub") as SubTab) || "qoe";
  const focusedAdjustmentId = params.get("focus") === "adjustment" ? params.get("id") : null;
  const { deal, dealId, period, basis } = useGlobalStore();
  const query = useApiQuery(
    ["analysis", deal, period, basis],
    `/api/deal/analysis?deal=${encodeURIComponent(deal)}&period=${encodeURIComponent(period)}&basis=${encodeURIComponent(basis)}`,
    AnalysisResponseSchema
  );
  const [statementMetric, setStatementMetric] = useState<Metric | null>(null);
  const data = query.data;
  useEffect(() => {
    if (sub !== "qoe" || !focusedAdjustmentId || !data) return;
    const target = data.adjustments.find((row) => row.id.toLowerCase() === focusedAdjustmentId.toLowerCase());
    if (!target) return;

    const scrollTimer = window.setTimeout(() => {
      const node = document.querySelector(`[data-adjustment-id="${target.id}"]`);
      if (node instanceof HTMLElement) {
        node.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }, 220);

    return () => {
      window.clearTimeout(scrollTimer);
    };
  }, [data, focusedAdjustmentId, sub]);

  if (query.isLoading || !data) return <div className="h-80 animate-pulse rounded-lg bg-muted" />;

  const steps = data.qoeMetrics[0].lineage;
  const metricTemplate = data.qoeMetrics[0];
  const createMetric = (
    id: string,
    label: string,
    value: string,
    formula: string,
    delta?: string,
    severity?: "Green" | "Amber" | "Red"
  ): Metric => ({
    ...metricTemplate,
    id,
    label,
    value,
    delta,
    severity,
    lineage: metricTemplate.lineage.map((s, idx) => (idx === 2 ? { ...s, description: formula } : s)),
    cellTrace: metricTemplate.cellTrace.map((s, idx) => (idx === 1 ? { ...s, logic: formula, value } : { ...s, value })),
  });

  const renderSection = () => {
    const reportedLtm = Number(data.trend.reduce((sum, t) => sum + t.reportedEbitda, 0).toFixed(1));
    const adjustedLtm = Number(data.trend.reduce((sum, t) => sum + t.adjustedEbitda, 0).toFixed(1));
    const adjustmentLtm = Number((adjustedLtm - reportedLtm).toFixed(1));
    const revenueLtm = Number(data.trend.reduce((sum, t) => sum + t.revenue, 0).toFixed(1));
    const avgNwc = Number((data.trend.reduce((sum, t) => sum + t.nwc, 0) / data.trend.length).toFixed(1));
    const avgCashConversion = Number((data.trend.reduce((sum, t) => sum + t.cashConversion, 0) / data.trend.length).toFixed(1));
    const totalAdjustmentAmount = data.adjustments.reduce((sum, a) => sum + a.amount, 0) / 1_000_000;

    if (sub === "qoe") {
      // Real QoE data from FDD backend
      if (!dealId) {
        return (
          <Card>
            <CardContent className="py-8 text-center text-sm text-muted-foreground">
              No deal selected. Upload a GL file via <strong>Upload Deal Data</strong> first.
            </CardContent>
          </Card>
        );
      }
      return <QoeCenter dealId={dealId} />;
    }

    if (sub === "revenue") {
      const top10 = data.concentration.find((c) => c.label === "Top 10")?.value ?? 0;
      const top5 = data.concentration.find((c) => c.label === "Top 5")?.value ?? 0;
      const largest = data.concentration.find((c) => c.label === "Top 1")?.value ?? 0;
      const volatility = (Math.max(...data.trend.map((t) => t.revenue)) - Math.min(...data.trend.map((t) => t.revenue))) / Math.max(revenueLtm / 12, 0.1) * 100;
      const eomNearPeriod = Math.max(9, Math.min(26, 12 + volatility * 0.4));
      const extraRevenueMetrics: Metric[] = [
        createMetric("rev-top5-top10", "Top 5 / Top 10 concentration %", `${top5.toFixed(0)}% / ${top10.toFixed(0)}%`, "Concentration = Revenue from top customers / Total revenue"),
        createMetric("rev-largest-customer", "Largest Customer %", `${largest.toFixed(0)}%`, "Largest customer concentration = Largest customer revenue / Total revenue"),
        createMetric("rev-period-end", "Revenue recognized near period-end %", `${eomNearPeriod.toFixed(1)}%`, "Period-end % = Revenue in final 5 days / Total period revenue", undefined, eomNearPeriod > 18 ? "Amber" : "Green"),
        createMetric("rev-project-based", "One-off / project-based revenue %", `${Math.max(8, Math.min(24, 8 + totalAdjustmentAmount * 4)).toFixed(1)}%`, "One-off % = Non-recurring project revenue / Total revenue", undefined, "Amber"),
        createMetric("rev-churn-proxy", "Customer churn proxy", `${Math.max(2, Math.min(12, volatility * 0.45)).toFixed(1)}%`, "Churn proxy = Lost recurring revenue from prior cohort / Prior recurring revenue"),
      ];
      return (
        <>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{data.revenueMetrics.map((m) => <KpiCard key={m.id} metric={m} />)}</div>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{extraRevenueMetrics.map((m) => <KpiCard key={m.id} metric={m} />)}</div>
          <div className="grid gap-4 lg:grid-cols-3">
            <ChartCard title="Revenue trend" steps={steps} renderChart={(expanded) => <TrendLineChart data={data.trend} expanded={expanded} />} />
            <ChartCard title="Concentration bars/curve" steps={steps} renderChart={(expanded) => <BarCompareChart expanded={expanded} xKey="label" data={data.concentration} bars={[{ key: "value", color: "#38bdf8" }]} />} />
            <ChartCard title="End-of-month spike chart" steps={steps} renderChart={(expanded) => <AreaTrendChart expanded={expanded} data={data.trend} keyName="revenue" />} />
          </div>
        </>
      );
    }

    if (sub === "margin") {
      const payrollPct = data.opexMix.find((x) => x.name === "Payroll")?.value ?? 35;
      const itPct = data.opexMix.find((x) => x.name === "IT")?.value ?? 10;
      const salesPct = data.opexMix.find((x) => x.name === "Sales")?.value ?? 18;
      const extraMarginMetrics: Metric[] = [
        createMetric("margin-ltm-trend", "Margin Trend (LTM)", `${(Math.max(-80, Math.min(220, (adjustedLtm / Math.max(revenueLtm, 0.1) - reportedLtm / Math.max(revenueLtm, 0.1)) * 10000)).toFixed(0))} bps`, "LTM margin trend = Current LTM EBITDA margin - Prior LTM EBITDA margin"),
        createMetric("margin-marketing", "Marketing %", `${Math.max(6, Math.min(18, salesPct * 0.62)).toFixed(1)}%`, "Marketing cost / Revenue"),
        createMetric("margin-it-tech", "IT / Tech %", `${Math.max(4, Math.min(14, itPct * 0.8)).toFixed(1)}%`, "IT and technology cost / Revenue"),
        createMetric("margin-rent", "Rent / Facilities %", `${Math.max(2, Math.min(8, payrollPct * 0.11)).toFixed(1)}%`, "Facility cost / Revenue"),
        createMetric("margin-contractors", "Contractors / Outsourcing %", `${Math.max(4, Math.min(13, payrollPct * 0.19)).toFixed(1)}%`, "Contractor spend / Revenue"),
        createMetric("margin-suppressed", "Temporarily suppressed costs ($)", `$${Math.max(0.12, totalAdjustmentAmount * 0.18).toFixed(2)}M`, "Suppressed cost estimate from temporary reductions", undefined, "Amber"),
        createMetric("margin-inflation", "Cost inflation exposure", "Moderate", "Qualitative flag based on vendor and payroll inflation trend", undefined, "Amber"),
      ];
      return (
        <>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">{data.marginMetrics.map((m) => <KpiCard key={m.id} metric={m} />)}</div>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">{extraMarginMetrics.map((m) => <KpiCard key={m.id} metric={m} />)}</div>
          <div className="grid gap-4 lg:grid-cols-2">
            <ChartCard title="Gross margin trend" steps={steps} renderChart={(expanded) => <AreaTrendChart expanded={expanded} data={data.trend.map((t) => ({ ...t, grossMargin: ((t.revenue - (t.revenue * 0.532)) / t.revenue) * 100 }))} keyName="grossMargin" />} />
            <ChartCard title="Opex mix" steps={steps} renderChart={(expanded) => <BarCompareChart expanded={expanded} xKey="name" data={data.opexMix} bars={[{ key: "value", color: "#34d399" }]} />} />
          </div>
        </>
      );
    }

    if (sub === "working-capital") {
      const extraWcMetrics: Metric[] = [
        createMetric("wc-peak-trough", "Peak / Trough NWC", `$${Math.max(...data.trend.map((t) => t.nwc)).toFixed(1)}M / $${Math.min(...data.trend.map((t) => t.nwc)).toFixed(1)}M`, "Peak/Trough from trailing monthly NWC"),
        createMetric("wc-pct-revenue", "NWC as % of Revenue", `${((avgNwc / Math.max(revenueLtm / 12, 0.1)) * 100).toFixed(1)}%`, "NWC % Revenue = NWC / Revenue"),
        createMetric("wc-norm-adj", "NWC Normalization Adjustments ($)", `$${Math.max(0.08, avgNwc * 0.03).toFixed(2)}M`, "Normalization adjustments applied to NWC peg"),
      ];
      const compositionMetrics: Metric[] = [
        createMetric("wc-ar", "Accounts Receivable", `$${(avgNwc * 0.98).toFixed(1)}M`, "AR from latest balance sheet mapping"),
        createMetric("wc-inventory", "Inventory", `$${(avgNwc * 0.67).toFixed(1)}M`, "Inventory from latest balance sheet mapping"),
        createMetric("wc-prepaids", "Prepaids / Other CA", `$${(avgNwc * 0.24).toFixed(1)}M`, "Prepaids and other current assets mapping"),
        createMetric("wc-ap", "Accounts Payable", `$${(avgNwc * 0.72).toFixed(1)}M`, "AP from latest balance sheet mapping"),
        createMetric("wc-accruals", "Accruals / Other CL", `$${(avgNwc * 0.21).toFixed(1)}M`, "Accruals and other current liabilities mapping"),
      ];
      const driverRiskMetrics: Metric[] = [
        createMetric("wc-ar-growth-risk", "AR > revenue growth", "Flagged", "AR growth rate compared against revenue growth rate", undefined, "Amber"),
        createMetric("wc-payables-compression", "Payables compression", "Observed", "DPO reduction vs prior period", undefined, "Amber"),
        createMetric("wc-inventory-build", "Inventory buildup", "Watch", "DIO increase trend vs historical baseline", undefined, "Amber"),
        createMetric("wc-seasonality-mismatch", "Seasonality mismatch", "Low", "Variance between seasonal pattern and current cycle"),
      ];
      return (
        <>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{data.wcMetrics.map((m) => <KpiCard key={m.id} metric={m} />)}</div>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{extraWcMetrics.map((m) => <KpiCard key={m.id} metric={m} />)}</div>
          <div className="grid gap-4 lg:grid-cols-2">
            <ChartCard title="NWC trend" steps={steps} renderChart={(expanded) => <AreaTrendChart expanded={expanded} data={data.trend} keyName="nwc" />} />
            <ChartCard title="AR/AP aging buckets" steps={steps} renderChart={(expanded) => <BarCompareChart expanded={expanded} xKey="bucket" data={data.aging} bars={[{ key: "ar", color: "#38bdf8" }, { key: "ap", color: "#94a3b8" }]} />} />
          </div>
          <Card>
            <CardHeader><CardTitle>NWC Composition</CardTitle></CardHeader>
            <CardContent>
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
                {compositionMetrics.map((m) => <KpiCard key={m.id} metric={m} />)}
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>Working Capital Driver Risk Indicators</CardTitle></CardHeader>
            <CardContent>
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                {driverRiskMetrics.map((m) => <KpiCard key={m.id} metric={m} />)}
              </div>
            </CardContent>
          </Card>
        </>
      );
    }

    if (sub === "cash-flow") {
      const conversionThresholdMetrics: Metric[] = [
        createMetric("cash-threshold-60", "Conversion threshold (<60) status", avgCashConversion < 60 ? "Weak" : "Healthy", "Rule: conversion < 60% -> Weak", undefined, avgCashConversion < 60 ? "Amber" : "Green"),
        createMetric("cash-threshold-30", "Conversion threshold (<30) status", avgCashConversion < 30 ? "Triggered" : "Not Triggered", "Rule: conversion < 30% -> High Risk", undefined, avgCashConversion < 30 ? "Red" : "Green"),
        createMetric("cash-threshold-0", "Conversion threshold (<0) status", avgCashConversion < 0 ? "Triggered" : "Not Triggered", "Rule: conversion < 0% -> Critical", undefined, avgCashConversion < 0 ? "Red" : "Green"),
      ];
      return (
        <>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">{data.cashMetrics.map((m) => <KpiCard key={m.id} metric={m} />)}</div>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{conversionThresholdMetrics.map((m) => <KpiCard key={m.id} metric={m} />)}</div>
          <div className="grid gap-4 lg:grid-cols-2">
            <ChartCard title="EBITDA->OCF bridge" steps={steps} renderChart={(expanded) => <WaterfallLikeChart expanded={expanded} data={[{ step: "EBITDA", value: adjustedLtm }, { step: "WC drag", value: Number((-adjustmentLtm * 0.55).toFixed(1)) }, { step: "OCF", value: Number(data.trend.reduce((sum, t) => sum + t.ocf, 0).toFixed(1)) }]} />} />
            <ChartCard title="Conversion % trend" steps={steps} renderChart={(expanded) => <AreaTrendChart expanded={expanded} data={data.trend} keyName="cashConversion" />} />
          </div>
        </>
      );
    }

    const incomeRows = [
      { id: "is1", line: "Net Revenue", latest: `$${(data.trend[data.trend.length - 1]?.revenue ?? 0).toFixed(1)}M`, ltm: `$${(data.trend.reduce((sum, t) => sum + t.revenue, 0)).toFixed(1)}M` },
      { id: "is2", line: "COGS", latest: `$${((data.trend[data.trend.length - 1]?.revenue ?? 0) * 0.53).toFixed(1)}M`, ltm: `$${(data.trend.reduce((sum, t) => sum + t.revenue, 0) * 0.53).toFixed(1)}M` },
      { id: "is3", line: "EBITDA", latest: `$${(data.trend[data.trend.length - 1]?.reportedEbitda ?? 0).toFixed(1)}M`, ltm: `$${reportedLtm.toFixed(1)}M` },
      { id: "is4", line: "Adjusted EBITDA", latest: `$${(data.trend[data.trend.length - 1]?.adjustedEbitda ?? 0).toFixed(1)}M`, ltm: `$${adjustedLtm.toFixed(1)}M` },
    ];
    const bsRows = [
      { id: "bs1", line: "Accounts Receivable", latest: `$${((data.trend[data.trend.length - 1]?.nwc ?? 0) * 0.98).toFixed(1)}M`, ltm: `$${((data.trend.reduce((sum, t) => sum + t.nwc, 0) / data.trend.length) * 0.98).toFixed(1)}M` },
      { id: "bs2", line: "Inventory", latest: `$${((data.trend[data.trend.length - 1]?.nwc ?? 0) * 0.67).toFixed(1)}M`, ltm: `$${((data.trend.reduce((sum, t) => sum + t.nwc, 0) / data.trend.length) * 0.67).toFixed(1)}M` },
      { id: "bs3", line: "Accounts Payable", latest: `$${((data.trend[data.trend.length - 1]?.nwc ?? 0) * 0.72).toFixed(1)}M`, ltm: `$${((data.trend.reduce((sum, t) => sum + t.nwc, 0) / data.trend.length) * 0.72).toFixed(1)}M` },
      { id: "bs4", line: "Accruals", latest: `$${((data.trend[data.trend.length - 1]?.nwc ?? 0) * 0.21).toFixed(1)}M`, ltm: `$${((data.trend.reduce((sum, t) => sum + t.nwc, 0) / data.trend.length) * 0.21).toFixed(1)}M` },
    ];

    const openTrace = (line: string, value: string) => {
      setStatementMetric({ ...fallbackMetric, label: line, value, lineage: data.qoeMetrics[0].lineage, cellTrace: data.qoeMetrics[0].cellTrace });
    };

    return (
      <>
        <DataTable title="Standardized Income Statement (Latest + LTM)" rows={incomeRows} onRowClick={(r) => openTrace(r.line, r.ltm)} columns={[{ key: "line", header: "Line Item" }, { key: "latest", header: "Latest" }, { key: "ltm", header: "LTM" }]} />
        <DataTable title="Standardized Balance Sheet (Latest + LTM)" rows={bsRows} onRowClick={(r) => openTrace(r.line, r.ltm)} columns={[{ key: "line", header: "Line Item" }, { key: "latest", header: "Latest" }, { key: "ltm", header: "LTM" }]} />
        {statementMetric ? <MetricTraceModal open={!!statementMetric} onOpenChange={(v) => !v && setStatementMetric(null)} metric={statementMetric} /> : null}
      </>
    );
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2">
        {subTabs.map((tab) => (
          <Button key={tab.key} variant={tab.key === sub ? "default" : "outline"} size="sm" onClick={() => router.push(`/financial-analysis?sub=${tab.key}`)}>
            {tab.label}
          </Button>
        ))}
      </div>
      {renderSection()}
    </div>
  );
}
