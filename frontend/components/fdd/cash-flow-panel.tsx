"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { getCashFlow, type CashFlowStatement } from "@/lib/api/fdd-client";
import { AreaTrendChart, BarCompareChart } from "@/components/charts/common-charts";
import { lookupByPeriod } from "@/lib/utils/format";

const fmt = (v: string | number) => `$${(Math.abs(Number(v)) / 1_000_000).toFixed(2)}M`;

export function CashFlowPanel({ dealId }: { dealId: string }) {
  const [cf, setCf] = useState<CashFlowStatement | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    getCashFlow(dealId)
      .then(setCf)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [dealId]);

  if (loading) return <Skeleton className="h-64 w-full" />;
  if (error || !cf) {
    return (
      <Card className="border-dashed">
        <CardContent className="py-8 text-center text-sm text-muted-foreground">
          {error ?? "Cash flow statement unavailable for this deal."}
        </CardContent>
      </Card>
    );
  }

  const periods = cf.periods;
  const ocfAt = (p: string) => Number(lookupByPeriod(cf.operating_cash_flow, p) ?? 0);
  const investingAt = (p: string) => Number(lookupByPeriod(cf.investing_cash_flow, p) ?? 0);
  const conversionAt = (p: string) => lookupByPeriod(cf.cash_conversion, p) ?? null;

  const ltmOcf = periods.reduce((s, p) => s + ocfAt(p), 0);
  const ltmInvesting = periods.reduce((s, p) => s + investingAt(p), 0);
  const negativeMonths = periods.filter((p) => ocfAt(p) < 0).length;
  const conversions = periods.map(conversionAt).filter((v): v is number => v !== null);
  const avgConversion = conversions.length ? (conversions.reduce((s, v) => s + v, 0) / conversions.length) * 100 : null;

  const conversionTrend = periods.map((p) => {
    const c = conversionAt(p);
    return { month: p, conversion: c !== null ? Number((c * 100).toFixed(1)) : 0 };
  });
  const cashFlowTrend = periods.map((p) => ({
    month: p,
    operating: Number((ocfAt(p) / 1_000_000).toFixed(2)),
    investing: Number((investingAt(p) / 1_000_000).toFixed(2)),
  }));

  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card><CardContent className="pt-5"><p className="text-xs text-muted-foreground uppercase">Operating CF (full history)</p><p className="mt-1 text-xl font-bold">{fmt(ltmOcf)}</p></CardContent></Card>
        <Card><CardContent className="pt-5"><p className="text-xs text-muted-foreground uppercase">Investing CF (full history)</p><p className="mt-1 text-xl font-bold">{fmt(ltmInvesting)}</p></CardContent></Card>
        <Card><CardContent className="pt-5"><p className="text-xs text-muted-foreground uppercase">Avg. Cash Conversion</p><p className="mt-1 text-xl font-bold">{avgConversion !== null ? `${avgConversion.toFixed(0)}%` : "—"}</p></CardContent></Card>
        <Card><CardContent className="pt-5"><p className="text-xs text-muted-foreground uppercase">Negative OCF Months</p><p className="mt-1 text-xl font-bold">{negativeMonths}</p></CardContent></Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle className="text-sm font-semibold">Cash Conversion % Trend</CardTitle></CardHeader>
          <CardContent><AreaTrendChart data={conversionTrend} keyName="conversion" /></CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="text-sm font-semibold">Operating vs Investing Cash Flow ($M)</CardTitle></CardHeader>
          <CardContent>
            <BarCompareChart
              data={cashFlowTrend}
              xKey="month"
              bars={[
                { key: "operating", color: "#38bdf8" },
                { key: "investing", color: "#94a3b8" },
              ]}
            />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader><CardTitle className="text-sm font-semibold">Conversion Threshold Status</CardTitle></CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-3">
          {[
            { label: "< 60% — Weak", triggered: avgConversion !== null && avgConversion < 60 },
            { label: "< 30% — High Risk", triggered: avgConversion !== null && avgConversion < 30 },
            { label: "< 0% — Critical", triggered: avgConversion !== null && avgConversion < 0 },
          ].map((t) => (
            <div key={t.label} className={`rounded border p-3 text-center text-sm ${t.triggered ? "border-rose-400 bg-rose-50 text-rose-700 dark:bg-rose-500/10" : "bg-card"}`}>
              {t.label}: {t.triggered ? "Triggered" : "Not Triggered"}
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
