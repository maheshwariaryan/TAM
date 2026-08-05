"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { AlertCircle } from "lucide-react";
import { AreaTrendChart, BarCompareChart } from "@/components/charts/common-charts";
import { getCommercialHealth, getPnL, type CommercialHealthReport, type PnLStatement } from "@/lib/api/fdd-client";

const fmtPct = (v: number | null) => (v === null ? "—" : `${v.toFixed(1)}%`);

export function MarginPanel({ dealId }: { dealId: string }) {
  const [commercial, setCommercial] = useState<CommercialHealthReport | null>(null);
  const [pnl, setPnl] = useState<PnLStatement | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    Promise.allSettled([getCommercialHealth(dealId), getPnL(dealId)]).then(([c, p]) => {
      setCommercial(c.status === "fulfilled" ? c.value : null);
      setPnl(p.status === "fulfilled" ? p.value : null);
      if (c.status === "rejected" && p.status === "rejected") {
        setError("Margin data unavailable for this deal.");
      }
      setLoading(false);
    });
  }, [dealId]);

  if (loading) return (
    <div className="space-y-4">
      <Skeleton className="h-32 w-full" />
      <Skeleton className="h-64 w-full" />
    </div>
  );

  if (error) return (
    <Card className="border-destructive">
      <CardContent className="flex items-center gap-3 py-6 text-destructive">
        <AlertCircle className="h-5 w-5 shrink-0" />
        <span className="text-sm">{error}</span>
      </CardContent>
    </Card>
  );

  if (!pnl || pnl.periods.length === 0) {
    return (
      <Card className="border-dashed">
        <CardContent className="py-8 text-center text-sm text-muted-foreground">
          {commercial?.message ?? "P&L unavailable — run the financial_builder stage for this deal first."}
        </CardContent>
      </Card>
    );
  }

  const latestPeriod = pnl.periods[pnl.periods.length - 1];
  const latestPeriodKey = latestPeriod.slice(0, 7);
  const latestRevenue = Number(pnl.revenue[latestPeriodKey] ?? 0);
  const latestGrossMargin = pnl.gross_margin[latestPeriodKey] ?? null;
  const latestEbitdaMargin = pnl.ebitda_margin[latestPeriodKey] ?? null;

  const latestOpexRows = pnl.rows.filter((r) => r.period === latestPeriod && r.is_opex);
  const latestCogsTotal = pnl.rows
    .filter((r) => r.period === latestPeriod && r.is_cogs)
    .reduce((sum, r) => sum + Math.abs(Number(r.amount)), 0);
  const opexTotal = latestOpexRows.reduce((sum, r) => sum + Math.abs(Number(r.amount)), 0);

  // Category-level opex mix for the latest period, sorted largest-first — whatever
  // categories actually exist in this deal's mapped GL, not a fixed hardcoded list.
  const opexByCategory = new Map<string, number>();
  for (const row of latestOpexRows) {
    opexByCategory.set(row.category, (opexByCategory.get(row.category) ?? 0) + Math.abs(Number(row.amount)));
  }
  const opexMixData = [...opexByCategory.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8)
    .map(([name, amount]) => ({
      name,
      pctOfRevenue: latestRevenue ? Number(((amount / latestRevenue) * 100).toFixed(1)) : 0,
    }));

  const marginTrendData = commercial
    ? Object.keys(commercial.gross_margin_trend_pct)
        .sort()
        .map((period) => ({
          month: period,
          grossMargin: Number(commercial.gross_margin_trend_pct[period]?.toFixed(1) ?? 0),
          ebitdaMargin: Number(commercial.ebitda_margin_trend_pct[period]?.toFixed(1) ?? 0),
        }))
    : [];

  return (
    <div className="space-y-4">
      {commercial && commercial.unavailable_metrics.length > 0 && (
        <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:border-amber-500/40 dark:bg-amber-500/10 dark:text-amber-300">
          {commercial.message}
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card><CardContent className="pt-5"><p className="text-xs text-muted-foreground uppercase">Gross Margin</p><p className="mt-1 text-xl font-bold">{fmtPct(latestGrossMargin !== null ? latestGrossMargin * 100 : null)}</p></CardContent></Card>
        <Card><CardContent className="pt-5"><p className="text-xs text-muted-foreground uppercase">EBITDA Margin</p><p className="mt-1 text-xl font-bold">{fmtPct(latestEbitdaMargin !== null ? latestEbitdaMargin * 100 : null)}</p></CardContent></Card>
        <Card><CardContent className="pt-5"><p className="text-xs text-muted-foreground uppercase">COGS % of Revenue</p><p className="mt-1 text-xl font-bold">{fmtPct(latestRevenue ? (latestCogsTotal / latestRevenue) * 100 : null)}</p></CardContent></Card>
        <Card><CardContent className="pt-5"><p className="text-xs text-muted-foreground uppercase">Opex % of Revenue</p><p className="mt-1 text-xl font-bold">{fmtPct(latestRevenue ? (opexTotal / latestRevenue) * 100 : null)}</p></CardContent></Card>
      </div>

      {commercial && (
        <div className="grid gap-4 sm:grid-cols-2">
          <Card><CardContent className="pt-5"><p className="text-xs text-muted-foreground uppercase">Revenue Volatility</p><p className="mt-1 text-xl font-bold">{commercial.revenue_volatility !== null ? `${(commercial.revenue_volatility * 100).toFixed(0)}%` : "—"}</p><p className="text-xs text-muted-foreground">coefficient of variation</p></CardContent></Card>
          <Card>
            <CardContent className="pt-5">
              <p className="text-xs text-muted-foreground uppercase">Seasonality</p>
              <p className="mt-1 text-xl font-bold">{commercial.seasonality_detected ? "Detected" : "Not detected"}</p>
              {commercial.seasonality_note && <p className="text-xs text-muted-foreground">{commercial.seasonality_note}</p>}
            </CardContent>
          </Card>
        </div>
      )}

      {marginTrendData.length > 0 && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader><CardTitle className="text-sm font-semibold">Gross Margin Trend (%)</CardTitle></CardHeader>
            <CardContent><AreaTrendChart data={marginTrendData} keyName="grossMargin" /></CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle className="text-sm font-semibold">EBITDA Margin Trend (%)</CardTitle></CardHeader>
            <CardContent><AreaTrendChart data={marginTrendData} keyName="ebitdaMargin" /></CardContent>
          </Card>
        </div>
      )}

      {opexMixData.length > 0 && (
        <Card>
          <CardHeader><CardTitle className="text-sm font-semibold">Opex Mix by Category ({latestPeriodKey}, % of revenue)</CardTitle></CardHeader>
          <CardContent>
            <BarCompareChart data={opexMixData} xKey="name" bars={[{ key: "pctOfRevenue", color: "#34d399" }]} />
          </CardContent>
        </Card>
      )}
    </div>
  );
}
