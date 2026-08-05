"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { getTieOuts, type CrossDocumentValidation } from "@/lib/api/fdd-client";

const fmt = (v: string) => `$${Math.abs(Number(v)).toLocaleString("en-US", { maximumFractionDigits: 0 })}`;

const statusClass: Record<string, string> = {
  Pass: "bg-emerald-100 text-emerald-700",
  Warn: "bg-amber-100 text-amber-700",
  Fail: "bg-rose-100 text-rose-700",
};

export function TieOutsPanel({ dealId }: { dealId: string }) {
  const [data, setData] = useState<CrossDocumentValidation | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    getTieOuts(dealId)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [dealId]);

  if (loading) return <Skeleton className="h-40 w-full" />;

  if (!data || data.tie_outs.length === 0) {
    return (
      <Card className="border-dashed">
        <CardContent className="py-6 text-center text-sm text-muted-foreground">
          No cross-document tie-outs available — upload AR/AP aging alongside the GL to enable reconciliation checks.
        </CardContent>
      </Card>
    );
  }

  const passCount = data.tie_outs.filter((t) => t.status === "Pass").length;
  const warnCount = data.tie_outs.filter((t) => t.status === "Warn").length;
  const failCount = data.tie_outs.filter((t) => t.status === "Fail").length;
  const maxVariance = Math.max(...data.tie_outs.map((t) => Math.max(t.variance_pct, t.tolerance_pct)), 1);
  const barFillClass: Record<string, string> = {
    Pass: "bg-emerald-500",
    Warn: "bg-amber-500",
    Fail: "bg-rose-500",
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-2 text-center text-xs">
        <div className="rounded bg-emerald-100 p-2 text-emerald-800 dark:bg-emerald-500/20 dark:text-emerald-200"><p className="font-semibold">{passCount}</p><p>Pass</p></div>
        <div className="rounded bg-amber-100 p-2 text-amber-800 dark:bg-amber-500/20 dark:text-amber-200"><p className="font-semibold">{warnCount}</p><p>Warn</p></div>
        <div className="rounded bg-rose-100 p-2 text-rose-800 dark:bg-rose-500/20 dark:text-rose-200"><p className="font-semibold">{failCount}</p><p>Fail</p></div>
      </div>

      <Card>
        <CardHeader><CardTitle className="text-sm font-semibold">Variance vs Tolerance</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          {data.tie_outs.map((row) => (
            <div key={row.name}>
              <div className="mb-1 flex items-center justify-between text-xs">
                <span className="font-medium">{row.name}</span>
                <span className="text-muted-foreground">{row.variance_pct.toFixed(2)}% vs {row.tolerance_pct.toFixed(2)}% tolerance</span>
              </div>
              <div className="relative h-2 overflow-hidden rounded-full bg-muted">
                <div className={`h-full ${barFillClass[row.status]}`} style={{ width: `${Math.min(100, (row.variance_pct / maxVariance) * 100)}%` }} />
                <div className="absolute top-0 h-2 w-0.5 bg-foreground/50" style={{ left: `${Math.min(100, (row.tolerance_pct / maxVariance) * 100)}%` }} />
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-sm font-semibold">Tie-Out Scoreboard</CardTitle></CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b text-xs text-muted-foreground">
                <th className="py-2 pr-4">Check</th>
                <th className="py-2 pr-4">Expected</th>
                <th className="py-2 pr-4">Observed</th>
                <th className="py-2 pr-4">Diff</th>
                <th className="py-2 pr-4">Variance %</th>
                <th className="py-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {data.tie_outs.map((row) => (
                <tr key={row.name} className="border-b border-border/50 last:border-0">
                  <td className="py-2 pr-4 font-medium">{row.name}</td>
                  <td className="py-2 pr-4">{fmt(row.expected)}</td>
                  <td className="py-2 pr-4">{fmt(row.observed)}</td>
                  <td className="py-2 pr-4">{fmt(row.difference)}</td>
                  <td className="py-2 pr-4">{row.variance_pct.toFixed(1)}%</td>
                  <td className="py-2">
                    <span className={`rounded-full px-2 py-1 text-xs font-semibold ${statusClass[row.status]}`}>{row.status}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {data.warnings.length > 0 && (
            <div className="mt-3 space-y-1">
              {data.warnings.map((w, i) => (
                <p key={i} className="text-xs text-amber-700 dark:text-amber-400">{w}</p>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
