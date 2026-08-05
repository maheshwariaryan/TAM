"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { AlertCircle } from "lucide-react";
import { getNetDebt, type NetDebtReport } from "@/lib/api/fdd-client";
import { cn } from "@/lib/utils/cn";
import { BridgeChart, type BridgeItem } from "@/components/charts/common-charts";

const fmt = (v: string | number | null) =>
  v === null ? "—" : `$${Math.abs(Number(v)).toLocaleString("en-US", { maximumFractionDigits: 0 })}`;

export function NetDebtPanel({ dealId }: { dealId: string }) {
  const [report, setReport] = useState<NetDebtReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    getNetDebt(dealId)
      .then(setReport)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [dealId]);

  if (loading) return <Skeleton className="h-64 w-full" />;

  if (error) return (
    <Card className="border-destructive">
      <CardContent className="flex items-center gap-3 py-6 text-destructive">
        <AlertCircle className="h-5 w-5 shrink-0" />
        <span className="text-sm">{error}</span>
      </CardContent>
    </Card>
  );

  if (!report || report.status === "skipped") {
    return (
      <Card className="border-dashed">
        <CardContent className="py-8 text-center text-sm text-muted-foreground">
          {report?.message ?? "Net debt bridge unavailable."}
        </CardContent>
      </Card>
    );
  }

  const bridgeItems: BridgeItem[] = report.bridge.map((c, idx) => ({
    label: c.label,
    amount: c.amount,
    type: c.is_subtotal ? "result" : idx === 0 ? "base" : Number(c.amount) < 0 ? "negative" : "positive",
  }));

  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-3">
        <Card>
          <CardContent className="pt-5">
            <p className="text-xs text-muted-foreground uppercase tracking-wide">Net Debt</p>
            <p className="mt-1 text-2xl font-bold">{fmt(report.net_debt)}</p>
            <p className="text-xs text-muted-foreground">as of {report.period}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-5">
            <p className="text-xs text-muted-foreground uppercase tracking-wide">Net Debt / LTM EBITDA</p>
            <p className="mt-1 text-2xl font-bold">
              {report.net_debt_to_ebitda !== null ? `${report.net_debt_to_ebitda.toFixed(2)}x` : "—"}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-5">
            <p className="text-xs text-muted-foreground uppercase tracking-wide">Cash &amp; Equivalents</p>
            <p className="mt-1 text-2xl font-bold">{fmt(report.cash_and_equivalents)}</p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader><CardTitle className="text-sm font-semibold">Net Debt Bridge</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <BridgeChart items={bridgeItems} />
          <div className="space-y-2">
            {report.bridge.map((c) => (
              <div key={c.label} className={cn("flex items-center justify-between rounded border px-3 py-2 text-sm", c.is_subtotal && "bg-muted/50 font-semibold")}>
                <span>{c.label}</span>
                <span className={Number(c.amount) < 0 ? "text-emerald-600" : ""}>{fmt(c.amount)}</span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {report.instruments.length > 0 && (
        <Card>
          <CardHeader><CardTitle className="text-sm font-semibold">Debt Instruments</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {report.reconciliation_note && (
              <p className="rounded-md border border-muted bg-muted/30 p-2 text-xs text-muted-foreground">
                {report.reconciliation_note}
              </p>
            )}
            {report.instruments.map((inst) => (
              <div key={inst.instrument_id} className="rounded-lg border bg-card p-3 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-medium">{inst.lender ?? "Unknown lender"} — {inst.facility_type.replace(/_/g, " ")}</span>
                  <span className="font-semibold">{fmt(inst.principal_outstanding)}</span>
                </div>
                <div className="mt-1 flex flex-wrap gap-4 text-xs text-muted-foreground">
                  {inst.interest_rate_pct && <span>Rate: {inst.interest_rate_pct}%</span>}
                  {inst.maturity_date && <span>Maturity: {inst.maturity_date}</span>}
                  <span>Source: {inst.source_document}</span>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
