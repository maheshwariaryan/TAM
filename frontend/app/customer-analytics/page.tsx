"use client";

import { KpiCard } from "@/components/kpi-card";
import { ChartCard } from "@/components/charts/chart-card";
import { BarCompareChart, TrendLineChart } from "@/components/charts/common-charts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useApiQuery } from "@/hooks/use-api-query";
import { CustomerResponseSchema } from "@/lib/schemas/types";
import { useGlobalStore } from "@/lib/store/use-global-store";

export default function CustomerAnalyticsPage() {
  const { deal, dealId, period, basis } = useGlobalStore();
  const query = useApiQuery(
    ["customer", deal, period, basis],
    `/api/deal/customer?deal=${encodeURIComponent(deal)}&period=${encodeURIComponent(period)}&basis=${encodeURIComponent(basis)}`,
    CustomerResponseSchema
  );

  // This system does not ingest customer-level invoice/revenue data, so there is no honest
  // way to compute concentration, churn, or discount-anomaly metrics for a real deal — show
  // that plainly rather than displaying the seeded mock numbers below.
  if (dealId) {
    return (
      <div className="space-y-5">
        <h2 className="text-xl font-semibold">Customer Analytics</h2>
        <Card className="border-dashed">
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            Customer analytics require customer-level invoice/revenue data, which is not part of this
            deal&apos;s uploaded data room. Upload a customer revenue schedule to enable concentration,
            NRR, and discount-anomaly analysis.
          </CardContent>
        </Card>
      </div>
    );
  }

  if (query.isLoading || !query.data) return <div className="h-80 animate-pulse rounded-lg bg-muted" />;
  if (query.data.metrics.length === 0) {
    return (
      <div className="rounded-lg border bg-card p-6 text-sm text-muted-foreground">
        No customer data available for the selected deal/period.
      </div>
    );
  }

  const steps = query.data.metrics[0].lineage;
  const trend = query.data.topTrend.map((r) => ({ month: r.month, revenue: r.top10, adjustedEbitda: r.top1 }));

  return (
    <div className="space-y-5">
      <h2 className="text-xl font-semibold">Customer Analytics</h2>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">{query.data.metrics.map((m) => <KpiCard key={m.id} metric={m} />)}</div>

      <div className="grid gap-4 lg:grid-cols-2">
        <ChartCard title="Revenue by top customers trend" steps={steps} renderChart={(expanded) => <TrendLineChart data={trend} expanded={expanded} />} />
        <ChartCard title="Discount anomaly monitor" steps={steps} renderChart={(expanded) => <BarCompareChart expanded={expanded} xKey="month" data={query.data.discountAnomalies.map((d) => ({ month: d.month, rate: Number((d.rate * 100).toFixed(2)), priorRate: Number((d.priorRate * 100).toFixed(2)) }))} bars={[{ key: "rate", color: "#fb923c" }, { key: "priorRate", color: "#94a3b8" }]} />} />
      </div>

      <Card>
        <CardHeader><CardTitle>Anomaly Rule Results</CardTitle></CardHeader>
        <CardContent className="space-y-2">
          {query.data.discountAnomalies.map((d) => (
            <div key={d.month} className="flex items-center justify-between rounded border bg-card p-2 text-sm">
              <span>{d.month}</span>
              <span>Current {(d.rate * 100).toFixed(2)}% vs Prior {(d.priorRate * 100).toFixed(2)}%</span>
              <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${d.flagged ? "bg-amber-100 text-amber-700" : "bg-emerald-100 text-emerald-700"}`}>
                {d.flagged ? "ORANGE" : "OK"}
              </span>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
