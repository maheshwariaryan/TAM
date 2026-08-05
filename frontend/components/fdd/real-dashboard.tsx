"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ChartCard } from "@/components/charts/chart-card";
import { AreaTrendChart, TrendLineChart } from "@/components/charts/common-charts";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import {
  getFinancialSummary,
  getQoE,
  getRedFlags,
  getNWC,
  getCashFlow,
  getDCF,
  type FinancialSummary,
  type QoEReport,
  type RedFlagReport,
  type NWCReport,
  type CashFlowStatement,
  type DCFReport,
} from "@/lib/api/fdd-client";
import { lookupByPeriod } from "@/lib/utils/format";

const fmtMoney = (v: string | number | null) =>
  v === null ? "—" : `$${(Math.abs(Number(v)) / 1_000_000).toFixed(1)}M`;

const SEVERITY_STYLE: Record<string, string> = {
  High: "bg-rose-100 text-rose-700",
  Medium: "bg-amber-100 text-amber-700",
  Low: "bg-blue-100 text-blue-700",
  Informational: "bg-slate-100 text-slate-700",
};

export function RealDashboard({ dealId }: { dealId: string }) {
  const [financials, setFinancials] = useState<FinancialSummary | null>(null);
  const [qoe, setQoe] = useState<QoEReport | null>(null);
  const [redflags, setRedflags] = useState<RedFlagReport | null>(null);
  const [nwc, setNwc] = useState<NWCReport | null>(null);
  const [cashFlow, setCashFlow] = useState<CashFlowStatement | null>(null);
  const [dcf, setDcf] = useState<DCFReport | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.allSettled([
      getFinancialSummary(dealId),
      getQoE(dealId),
      getRedFlags(dealId),
      getNWC(dealId),
      getCashFlow(dealId),
      getDCF(dealId),
    ]).then(([f, q, rf, n, cf, d]) => {
      setFinancials(f.status === "fulfilled" ? f.value : null);
      setQoe(q.status === "fulfilled" ? q.value : null);
      setRedflags(rf.status === "fulfilled" ? rf.value : null);
      setNwc(n.status === "fulfilled" ? n.value : null);
      setCashFlow(cf.status === "fulfilled" ? cf.value : null);
      setDcf(d.status === "fulfilled" ? d.value : null);
      setLoading(false);
    });
  }, [dealId]);

  if (loading) return <Skeleton className="h-96 w-full" />;

  if (!financials) {
    return (
      <Card className="border-dashed">
        <CardContent className="py-8 text-center text-sm text-muted-foreground">
          Financials not yet available — run /process on this deal first.
        </CardContent>
      </Card>
    );
  }

  const trend = financials.periods.map((pk) => ({
    month: pk,
    revenue: Number(financials.revenue[pk] ?? 0),
    adjustedEbitda: qoe ? Number(qoe.adjusted_ebitda[pk] ?? financials.ebitda[pk] ?? 0) : Number(financials.ebitda[pk] ?? 0),
  }));
  const topFlags = (redflags?.flags ?? []).filter((f) => f.severity === "High" || f.severity === "Medium").slice(0, 3);
  const nwcTrend = (nwc?.status === "complete" || nwc?.status === "partial")
    ? nwc.data_points.map((dp) => ({ month: dp.period, nwc: Number((Number(dp.net_working_capital) / 1_000_000).toFixed(2)) }))
    : [];
  const cashConversionTrend = cashFlow
    ? cashFlow.periods.map((p) => {
        const c = lookupByPeriod(cashFlow.cash_conversion, p) ?? null;
        return { month: p, conversion: c !== null ? Number((c * 100).toFixed(1)) : 0 };
      })
    : [];

  return (
    <div className="space-y-6">
      {dcf && dcf.status === "complete" && dcf.enterprise_value && (
        <div className="rounded-lg border bg-card p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Enterprise Value (DCF)</p>
              <p className="text-3xl font-semibold leading-tight tracking-tight text-foreground">{fmtMoney(dcf.enterprise_value)}</p>
            </div>
            {dcf.assumptions && (
              <p className="text-right text-sm text-muted-foreground">
                {(dcf.assumptions.discount_rate_annual * 100).toFixed(1)}% discount rate ·{" "}
                {(dcf.assumptions.terminal_growth_rate_annual * 100).toFixed(1)}% terminal growth
                <br />
                <span className="text-xs">directional cross-check only</span>
              </p>
            )}
          </div>
          {dcf.limitations.length > 0 && (
            <ul className="mt-3 space-y-1 border-t pt-3 text-xs text-muted-foreground">
              {dcf.limitations.map((limitation, i) => (
                <li key={i}>· {limitation}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <ChartCard
          title="Revenue & EBITDA Trend"
          steps={[]}
          renderChart={(expanded) => <TrendLineChart data={trend} expanded={expanded} />}
        />
        {nwcTrend.length > 0 && (
          <ChartCard
            title="NWC Trend"
            steps={[]}
            renderChart={(expanded) => <AreaTrendChart data={nwcTrend} keyName="nwc" expanded={expanded} />}
          />
        )}
        {cashConversionTrend.length > 0 && (
          <ChartCard
            title="Cash Conversion % Trend"
            steps={[]}
            renderChart={(expanded) => <AreaTrendChart data={cashConversionTrend} keyName="conversion" expanded={expanded} />}
          />
        )}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Top Red Flags</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {topFlags.length === 0 && (
              <p className="text-sm text-muted-foreground">No High/Medium severity red flags identified.</p>
            )}
            {topFlags.map((flag) => (
              <div key={flag.flag_id} className="rounded-md border bg-card p-3">
                <div className="mb-1 flex items-center justify-between gap-2">
                  <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${SEVERITY_STYLE[flag.severity]}`}>{flag.severity}</span>
                  <span className="text-xs text-muted-foreground">{flag.category}</span>
                </div>
                <p className="text-sm font-medium">{flag.title}</p>
              </div>
            ))}
            <Link href="/risk-assessment">
              <Button variant="outline" size="sm" className="w-full">View all red flags</Button>
            </Link>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Explore This Deal</CardTitle></CardHeader>
          <CardContent className="grid grid-cols-2 gap-2">
            <Link href="/financial-analysis"><Button variant="outline" className="w-full">Financial Analysis</Button></Link>
            <Link href="/risk-assessment"><Button variant="outline" className="w-full">Risk Assessment</Button></Link>
            <Link href="/documents"><Button variant="outline" className="w-full">Documents</Button></Link>
            <Link href="/reports"><Button variant="outline" className="w-full">Reports &amp; Databook</Button></Link>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
