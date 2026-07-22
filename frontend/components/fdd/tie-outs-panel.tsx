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

  return (
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
  );
}
