"use client";

import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useApiQuery } from "@/hooks/use-api-query";
import { InquiryResponseSchema, RiskResponseSchema } from "@/lib/schemas/types";
import { useGlobalStore } from "@/lib/store/use-global-store";
import { exportDatabook, getRedFlags, getTieOuts } from "@/lib/api/fdd-client";
import { JuniorAnalystReport } from "@/components/fdd/junior-analyst-report";

export default function ReportsPage() {
  const { deal, dealId, period, basis } = useGlobalStore();
  const [databookLoading, setDatabookLoading] = useState(false);
  const [databookError, setDatabookError] = useState<string | null>(null);
  const inquiryQuery = useApiQuery(
    ["inquiry-reports", deal, period, basis],
    `/api/deal/inquiry?deal=${encodeURIComponent(deal)}&period=${encodeURIComponent(period)}&basis=${encodeURIComponent(basis)}`,
    InquiryResponseSchema
  );
  const query = useApiQuery(
    ["risk-reports", deal, period, basis],
    `/api/deal/risk?deal=${encodeURIComponent(deal)}&period=${encodeURIComponent(period)}&basis=${encodeURIComponent(basis)}`,
    RiskResponseSchema
  );
  const [realReadiness, setRealReadiness] = useState<"Ready" | "Draft" | "Blocked" | null>(null);

  useEffect(() => {
    if (!dealId) {
      setRealReadiness(null);
      return;
    }
    Promise.allSettled([getRedFlags(dealId), getTieOuts(dealId)]).then(([rf, to]) => {
      const highCount = rf.status === "fulfilled" ? rf.value.summary.high : 0;
      const mediumCount = rf.status === "fulfilled" ? rf.value.summary.medium : 0;
      const tieOutFails = to.status === "fulfilled" ? to.value.tie_outs.filter((t) => t.status === "Fail").length : 0;
      const tieOutWarns = to.status === "fulfilled" ? to.value.tie_outs.filter((t) => t.status === "Warn").length : 0;
      if (highCount > 0 || tieOutFails > 0) setRealReadiness("Blocked");
      else if (mediumCount > 0 || tieOutWarns > 0) setRealReadiness("Draft");
      else setRealReadiness("Ready");
    });
  }, [dealId]);

  const handleDatabookExport = async () => {
    if (!dealId) {
      setDatabookError("No active deal. Upload and process files on the Upload page first.");
      return;
    }
    setDatabookLoading(true);
    setDatabookError(null);
    try {
      const filename = `${deal.replace(/\s+/g, "_")}_FDD_Databook.xlsx`;
      await exportDatabook(dealId, filename);
    } catch (err) {
      setDatabookError(err instanceof Error ? err.message : "Export failed");
    } finally {
      setDatabookLoading(false);
    }
  };

  const readiness = useMemo(() => {
    if (!query.data || !inquiryQuery.data) return "Draft";
    const blockingInquiries = inquiryQuery.data.inquiries.filter((i) => i.blocking && i.status !== "Closed").length;
    const failedTieOuts = query.data.tieOuts.filter((t) => t.status === "Fail").length;
    if (blockingInquiries > 0 || failedTieOuts > 0) return "Blocked";
    const warns = query.data.tieOuts.filter((t) => t.status === "Warn").length;
    return warns > 0 ? "Draft" : "Ready";
  }, [query.data, inquiryQuery.data]);

  const displayReadiness = dealId ? realReadiness : readiness;

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">Reports</h2>
        {displayReadiness && (
          <span className={`rounded-full px-3 py-1 text-sm font-semibold ${displayReadiness === "Ready" ? "bg-emerald-100 text-emerald-700" : displayReadiness === "Draft" ? "bg-amber-100 text-amber-700" : "bg-rose-100 text-rose-700"}`}>
            Report Readiness: {displayReadiness}
            {dealId ? " (from red flags + tie-outs)" : ""}
          </span>
        )}
      </div>

      <Card>
        <CardHeader><CardTitle>FDD Databook (Excel)</CardTitle></CardHeader>
        <CardContent className="space-y-2">
          <p className="text-sm text-muted-foreground">
            Multi-tab Excel export with QoE waterfall, adjustment ledger, GL mapping, tie-outs, and IRL.
          </p>
          <Button onClick={handleDatabookExport} disabled={databookLoading || !dealId}>
            {databookLoading ? "Generating..." : "Download FDD Databook (.xlsx)"}
          </Button>
          {!dealId ? (
            <p className="text-xs text-muted-foreground">Process a deal on the Upload page to enable export.</p>
          ) : null}
          {databookError ? <p className="text-xs text-rose-600">{databookError}</p> : null}
        </CardContent>
      </Card>

      {dealId ? (
        <JuniorAnalystReport dealId={dealId} deal={deal} />
      ) : (
        <Card>
          <CardHeader><CardTitle>No deal selected</CardTitle></CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              Process a deal on the Upload page to generate the Excel databook and narrative report.
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
