"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { AlertCircle } from "lucide-react";
import { AreaTrendChart, BarCompareChart } from "@/components/charts/common-charts";
import { getNWC, type NWCReport } from "@/lib/api/fdd-client";
import { cn } from "@/lib/utils/cn";

const fmt = (v: string | number | null) =>
  v === null ? "—" : `$${Math.abs(Number(v)).toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
const fmtDays = (v: number | null) => (v === null ? "—" : `${v.toFixed(0)}d`);
const fmtPct = (v: number | null) => (v === null ? "—" : `${v.toFixed(1)}%`);

export function NWCPanel({ dealId }: { dealId: string }) {
  const [report, setReport] = useState<NWCReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    getNWC(dealId)
      .then(setReport)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [dealId]);

  if (loading) return <div className="space-y-4"><Skeleton className="h-32 w-full" /><Skeleton className="h-64 w-full" /></div>;

  if (error) return (
    <Card className="border-destructive">
      <CardContent className="flex items-center gap-3 py-6 text-destructive">
        <AlertCircle className="h-5 w-5 shrink-0" />
        <span className="text-sm">{error}</span>
      </CardContent>
    </Card>
  );

  if (!report) return null;

  if (report.status === "skipped" || report.data_points.length === 0) {
    return (
      <Card className="border-dashed">
        <CardContent className="py-8 text-center text-sm text-muted-foreground">{report.message}</CardContent>
      </Card>
    );
  }

  const trendData = report.data_points.map((dp) => ({
    month: dp.period,
    nwc: Number(dp.net_working_capital) / 1_000_000,
  }));
  const recommendedPeg = report.pegs.find((p) => p.recommended) ?? report.pegs[0];
  const ratios = report.ratios;
  const latestPoint = report.data_points[report.data_points.length - 1];
  const toM = (v: string) => Number((Number(v) / 1_000_000).toFixed(2));
  const compositionData = [
    { name: "AR", value: toM(latestPoint.accounts_receivable) },
    { name: "Inventory", value: toM(latestPoint.inventory) },
    { name: "Prepaid + Other CA", value: toM(String(Number(latestPoint.prepaid_expenses) + Number(latestPoint.other_current_assets))) },
    { name: "AP", value: toM(latestPoint.accounts_payable) },
    { name: "Accrued Liab.", value: toM(latestPoint.accrued_liabilities) },
    { name: "Deferred Rev + Other CL", value: toM(String(Number(latestPoint.deferred_revenue) + Number(latestPoint.other_current_liabilities))) },
  ];

  return (
    <div className="space-y-4">
      {report.status === "partial" && (
        <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:border-amber-500/40 dark:bg-amber-500/10 dark:text-amber-300">
          {report.message}
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-3">
        <Card>
          <CardContent className="pt-5">
            <p className="text-xs text-muted-foreground uppercase tracking-wide">Recommended NWC Peg</p>
            <p className="mt-1 text-2xl font-bold">{fmt(recommendedPeg?.peg_amount ?? null)}</p>
            <p className="text-xs text-muted-foreground">{recommendedPeg?.method.replace(/_/g, " ")}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-5">
            <p className="text-xs text-muted-foreground uppercase tracking-wide">Peak / Trough NWC</p>
            <p className="mt-1 text-2xl font-bold">{fmt(report.peak_nwc)} / {fmt(report.trough_nwc)}</p>
            <p className="text-xs text-muted-foreground">{report.peak_period} / {report.trough_period}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-5">
            <p className="text-xs text-muted-foreground uppercase tracking-wide">NWC Volatility</p>
            <p className="mt-1 text-2xl font-bold">
              {report.nwc_volatility !== null ? `${(report.nwc_volatility * 100).toFixed(0)}%` : "—"}
            </p>
            <p className="text-xs text-muted-foreground">coefficient of variation</p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader><CardTitle className="text-sm font-semibold">NWC Peg Candidates</CardTitle></CardHeader>
        <CardContent className="space-y-2">
          {report.pegs.map((peg) => (
            <div key={peg.method} className={cn("rounded-lg border p-3", peg.recommended && "border-primary bg-primary/5")}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-sm font-medium">{peg.method.replace(/_/g, " ")}</span>
                <div className="flex items-center gap-2">
                  {peg.recommended && <Badge className="bg-primary/15 text-primary text-xs">Recommended</Badge>}
                  {peg.seasonality_detected && <Badge className="bg-amber-500/15 text-amber-600 text-xs">Seasonality detected</Badge>}
                  <span className="font-semibold">{fmt(peg.peg_amount)}</span>
                </div>
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                Range: {fmt(peg.confidence_interval_low)} – {fmt(peg.confidence_interval_high)}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">{peg.rationale}</p>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-sm font-semibold">NWC Trend</CardTitle></CardHeader>
        <CardContent><AreaTrendChart data={trendData} keyName="nwc" /></CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-sm font-semibold">NWC Composition ({latestPoint.period}, $M)</CardTitle></CardHeader>
        <CardContent>
          <BarCompareChart data={compositionData} xKey="name" bars={[{ key: "value", color: "#38bdf8" }]} />
        </CardContent>
      </Card>

      {ratios && (
        <Card>
          <CardHeader><CardTitle className="text-sm font-semibold">Working Capital Ratios ({ratios.period})</CardTitle></CardHeader>
          <CardContent>
            <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
              <div className="rounded border bg-card p-3 text-center"><p className="text-xs text-muted-foreground">DSO</p><p className="font-semibold">{fmtDays(ratios.dso_days)}</p></div>
              <div className="rounded border bg-card p-3 text-center"><p className="text-xs text-muted-foreground">DPO</p><p className="font-semibold">{fmtDays(ratios.dpo_days)}</p></div>
              <div className="rounded border bg-card p-3 text-center"><p className="text-xs text-muted-foreground">DIO</p><p className="font-semibold">{fmtDays(ratios.dio_days)}</p></div>
              <div className="rounded border bg-card p-3 text-center"><p className="text-xs text-muted-foreground">CCC</p><p className="font-semibold">{fmtDays(ratios.cash_conversion_cycle_days)}</p></div>
              <div className="rounded border bg-card p-3 text-center"><p className="text-xs text-muted-foreground">AR &gt;60d</p><p className="font-semibold">{fmtPct(ratios.ar_over_60d_pct)}</p></div>
              <div className="rounded border bg-card p-3 text-center"><p className="text-xs text-muted-foreground">AP &gt;60d</p><p className="font-semibold">{fmtPct(ratios.ap_over_60d_pct)}</p></div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
