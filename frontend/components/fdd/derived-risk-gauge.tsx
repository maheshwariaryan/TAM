"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { SeverityBadge } from "@/components/severity-badge";
import { getRedFlags, getTieOuts } from "@/lib/api/fdd-client";
import type { Severity } from "@/lib/schemas/types";

const clamp = (v: number, min: number, max: number) => Math.max(min, Math.min(max, v));

/**
 * Not a backend risk score — the FDD pipeline doesn't compute one. This is a
 * transparent client-side weighting of red-flag severity + tie-out exceptions,
 * both already visible on this page, so analysts get a scannable headline
 * number without us inventing a number the backend never produced.
 */
export function DerivedRiskGauge({ dealId }: { dealId: string }) {
  const [loading, setLoading] = useState(true);
  const [counts, setCounts] = useState<{ high: number; medium: number; fail: number; warn: number } | null>(null);

  useEffect(() => {
    setLoading(true);
    Promise.allSettled([getRedFlags(dealId), getTieOuts(dealId)]).then(([rf, tie]) => {
      const summary = rf.status === "fulfilled" ? rf.value.summary : { high: 0, medium: 0, low: 0, informational: 0, total: 0 };
      const tieOuts = tie.status === "fulfilled" ? tie.value.tie_outs : [];
      setCounts({
        high: summary.high,
        medium: summary.medium,
        fail: tieOuts.filter((t) => t.status === "Fail").length,
        warn: tieOuts.filter((t) => t.status === "Warn").length,
      });
      setLoading(false);
    });
  }, [dealId]);

  if (loading) return <Skeleton className="h-48 w-full" />;
  if (!counts) return null;

  const score = clamp(2 + counts.high * 1.8 + counts.medium * 0.6 + counts.fail * 1.5 + counts.warn * 0.5, 0, 10);
  const severity: Severity = score >= 7 ? "Red" : score >= 4.5 ? "Amber" : "Green";
  const gaugeFillPct = (score / 10) * 100;

  return (
    <Card>
      <CardHeader><CardTitle>Overall Deal Risk Indicator (derived)</CardTitle></CardHeader>
      <CardContent className="flex flex-wrap items-center gap-4">
        <div
          className="grid h-24 w-24 shrink-0 place-items-center rounded-full"
          style={{ aspectRatio: "1 / 1", background: `conic-gradient(#f97316 ${gaugeFillPct}%, #e2e8f0 ${gaugeFillPct}% 100%)` }}
        >
          <div className="grid h-16 w-16 shrink-0 place-items-center rounded-full bg-card text-lg font-bold" style={{ aspectRatio: "1 / 1" }}>
            {score.toFixed(1)}
          </div>
        </div>
        <div className="space-y-1">
          <SeverityBadge severity={severity} />
          <p className="text-sm text-muted-foreground">
            Derived from {counts.high} high-severity red flag{counts.high === 1 ? "" : "s"}, {counts.medium} medium-severity
            red flag{counts.medium === 1 ? "" : "s"}, {counts.fail} failed tie-out{counts.fail === 1 ? "" : "s"}, and{" "}
            {counts.warn} tie-out warning{counts.warn === 1 ? "" : "s"} below — not a backend-computed risk score.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
