"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { useApiQuery } from "@/hooks/use-api-query";
import { InquiryResponseSchema, RiskResponseSchema } from "@/lib/schemas/types";
import { useGlobalStore } from "@/lib/store/use-global-store";
import { exportDatabook } from "@/lib/api/fdd-client";

const exports = [
  "Independent Accountants Report (PDF)",
  "DCF Valuation Report (PDF)",
  "Red Flag Report (PDF)",
  "Financial Statements Report (PDF)",
  "QoE Report (PDF)",
  "Executive Summary (PDF)",
];

const exportMeta: Record<string, { filename: string; mime: string }> = {
  "Independent Accountants Report (PDF)": { filename: "TAM_Independent_Accountants_Report.pdf", mime: "application/pdf" },
  "DCF Valuation Report (PDF)": { filename: "TAM_DCF_Valuation_Report.pdf", mime: "application/pdf" },
  "Red Flag Report (PDF)": { filename: "TAM_Red_Flag_Report.pdf", mime: "application/pdf" },
  "Financial Statements Report (PDF)": { filename: "TAM_Financial_Statements_Report.pdf", mime: "application/pdf" },
  "QoE Report (PDF)": { filename: "TAM_QoE_Report.pdf", mime: "application/pdf" },
  "Executive Summary (PDF)": { filename: "TAM_Executive_Summary.pdf", mime: "application/pdf" },
};

export default function ReportsPage() {
  return (
    <Suspense fallback={<div className="h-80 animate-pulse rounded-lg bg-muted" />}>
      <ReportsPageContent />
    </Suspense>
  );
}

function ReportsPageContent() {
  const params = useSearchParams();
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
  const [open, setOpen] = useState(false);
  const [downloadingAll, setDownloadingAll] = useState(false);

  const triggerDownload = (filename: string, blob: Blob) => {
    const url = window.URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    window.URL.revokeObjectURL(url);
  };

  const downloadBlob = (filename: string, mime: string, content: string) => {
    const blob = new Blob([content], { type: mime });
    triggerDownload(filename, blob);
  };

  const generatePdfLikeContent = (item: string, stamp: string) => {
    const riskScore = query.data?.riskScore?.toFixed(1) ?? "N/A";
    const tieoutFails = query.data?.tieOuts.filter((t) => t.status === "Fail").length ?? 0;
    const tieoutWarns = query.data?.tieOuts.filter((t) => t.status === "Warn").length ?? 0;
    const blockingCount = inquiryQuery.data?.inquiries.filter((i) => i.blocking && i.status !== "Closed").length ?? 0;

    if (item === "Independent Accountants Report (PDF)") {
      return [
        "TAM INDEPENDENT ACCOUNTANTS REPORT",
        `Deal: ${deal}`,
        `Generated: ${stamp}`,
        "",
        "Opinion (mock): Based on procedures performed, financial schedules are fairly presented",
        "in all material respects, subject to unresolved blocking inquiries and tie-out exceptions.",
        "",
        `Report readiness: ${readiness}`,
        `Blocking inquiries: ${blockingCount}`,
        `Tie-out exceptions: ${tieoutFails} fail / ${tieoutWarns} warn`,
      ].join("\n");
    }

    if (item === "DCF Valuation Report (PDF)") {
      const impliedWacc = (9.2 + tieoutWarns * 0.25 + tieoutFails * 0.5).toFixed(2);
      const terminalGrowth = (2.1 - tieoutFails * 0.1).toFixed(2);
      return [
        "TAM DCF VALUATION REPORT",
        `Deal: ${deal}`,
        `Generated: ${stamp}`,
        "",
        "Valuation assumptions (mock):",
        `- WACC: ${impliedWacc}%`,
        `- Terminal Growth: ${terminalGrowth}%`,
        `- Risk Score Input: ${riskScore}/10`,
        "",
        "Conclusion (mock): Valuation range adjusted for QoE and risk concentration outcomes.",
      ].join("\n");
    }

    if (item === "Red Flag Report (PDF)") {
      return [
        "TAM RED FLAG REPORT",
        `Deal: ${deal}`,
        `Generated: ${stamp}`,
        "",
        "Priority findings (mock):",
        `- Tie-out fails: ${tieoutFails}`,
        `- Tie-out warns: ${tieoutWarns}`,
        `- Blocking inquiries: ${blockingCount}`,
        "",
        "Recommendation: resolve high-severity evidence gaps before final IC pack.",
      ].join("\n");
    }

    if (item === "Financial Statements Report (PDF)") {
      return [
        "TAM FINANCIAL STATEMENTS REPORT",
        `Deal: ${deal}`,
        `Generated: ${stamp}`,
        "",
        "Included schedules (mock):",
        "- Standardized Income Statement (latest + LTM)",
        "- Standardized Balance Sheet (latest + LTM)",
        "- Cash conversion and working capital bridge",
        "",
        "Prepared for diligence review and management discussion.",
      ].join("\n");
    }

    if (item === "QoE Report (PDF)") {
      return [
        "TAM QUALITY OF EARNINGS REPORT",
        `Deal: ${deal}`,
        `Generated: ${stamp}`,
        "",
        "Summary (mock): Reported EBITDA, Adjusted EBITDA, addbacks, and sustainability commentary.",
        `Risk linkage: score ${riskScore}/10 with readiness = ${readiness}.`,
      ].join("\n");
    }

    return [
      "TAM EXECUTIVE SUMMARY",
      `Deal: ${deal}`,
      `Generated: ${stamp}`,
      `Overall readiness: ${readiness}`,
      `Risk score: ${riskScore}/10`,
      `Open blockers: ${blockingCount}`,
    ].join("\n");
  };

  const handleExport = (item: string) => {
    const meta = exportMeta[item];
    if (!meta) return;
    const stamp = new Date().toISOString();
    downloadBlob(meta.filename, meta.mime, generatePdfLikeContent(item, stamp));
  };

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

  const handleDownloadAll = async () => {
    setDownloadingAll(true);
    try {
      const { default: JSZip } = await import("jszip");
      const zip = new JSZip();
      const stamp = new Date().toISOString();

      exports.forEach((item) => {
        const meta = exportMeta[item];
        if (!meta) return;
        zip.file(meta.filename, generatePdfLikeContent(item, stamp));
      });

      const blob = await zip.generateAsync({ type: "blob" });
      const zipName = `${deal.replace(/\s+/g, "_")}_TAM_Export_Pack.zip`;
      triggerDownload(zipName, blob);
    } finally {
      setDownloadingAll(false);
    }
  };

  useEffect(() => {
    if (params.get("exportPack") === "true") setOpen(true);
  }, [params]);

  const readiness = useMemo(() => {
    if (!query.data || !inquiryQuery.data) return "Draft";
    const blockingInquiries = inquiryQuery.data.inquiries.filter((i) => i.blocking && i.status !== "Closed").length;
    const failedTieOuts = query.data.tieOuts.filter((t) => t.status === "Fail").length;
    if (blockingInquiries > 0 || failedTieOuts > 0) return "Blocked";
    const warns = query.data.tieOuts.filter((t) => t.status === "Warn").length;
    return warns > 0 ? "Draft" : "Ready";
  }, [query.data, inquiryQuery.data]);

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">Reports</h2>
        <span className={`rounded-full px-3 py-1 text-sm font-semibold ${readiness === "Ready" ? "bg-emerald-100 text-emerald-700" : readiness === "Draft" ? "bg-amber-100 text-amber-700" : "bg-rose-100 text-rose-700"}`}>
          Report Readiness: {readiness}
        </span>
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

      <Card>
        <CardHeader><CardTitle>Export Center</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          {exports.map((item) => (
            <div key={item} className="flex items-center justify-between rounded border bg-card p-3">
              <p className="font-medium">{item}</p>
              <Button size="sm" variant="outline" onClick={() => handleExport(item)}>Export</Button>
            </div>
          ))}
          <Button onClick={() => setOpen(true)}>Export Pack</Button>
        </CardContent>
      </Card>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-2xl">
          <DialogTitle className="text-lg font-semibold">Export Pack Contents</DialogTitle>
          <div className="space-y-2 text-sm">
            <p>Included outputs:</p>
            <ul className="list-disc pl-5">
              {exports.map((item) => <li key={item}>{item}</li>)}
            </ul>
            <p>Pack also includes methodology notes, lineage snippets, and inquiry status appendix (mock).</p>
            <div className="pt-2">
              <Button onClick={handleDownloadAll} disabled={downloadingAll}>
                {downloadingAll ? "Preparing ZIP..." : "Download all (ZIP)"}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
