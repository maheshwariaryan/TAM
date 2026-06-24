"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DataTable } from "@/components/tables/data-table";
import { useApiQuery } from "@/hooks/use-api-query";
import { DocumentsResponseSchema, FileInventorySchema } from "@/lib/schemas/types";
import { formatDateTime } from "@/lib/utils/format";
import { z } from "zod";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { SeverityBadge } from "@/components/severity-badge";
import { DocumentUploadTool } from "@/components/documents/document-upload-tool";
import { useGlobalStore } from "@/lib/store/use-global-store";
import { X } from "lucide-react";

export default function DocumentsPage() {
  return (
    <Suspense fallback={<div className="h-80 animate-pulse rounded-lg bg-muted" />}>
      <DocumentsPageContent />
    </Suspense>
  );
}

function DocumentsPageContent() {
  const router = useRouter();
  const params = useSearchParams();
  const highlightedFile = params.get("file");
  const focusedCoverageSchedule = params.get("focus") === "coverage" ? params.get("schedule") : null;
  const focusedCoverageMonth = params.get("focus") === "coverage" ? params.get("month") : null;
  const { deal } = useGlobalStore();
  const query = useApiQuery(
    ["documents", deal],
    `/api/deal/documents?deal=${encodeURIComponent(deal)}`,
    DocumentsResponseSchema
  );
  const [selectedFile, setSelectedFile] = useState<z.infer<typeof FileInventorySchema> | null>(null);
  const [uploadedFiles, setUploadedFiles] = useState<z.infer<typeof FileInventorySchema>[]>([]);
  const [highlightedRowId, setHighlightedRowId] = useState<string | null>(null);
  const [highlightedCoverageKey, setHighlightedCoverageKey] = useState<string | null>(null);
  const storageKey = `tam-uploaded-files:${deal}`;
  const makeCoverageKey = (schedule: string, month: string) => `${schedule.toLowerCase()}::${month.toLowerCase()}`;

  const legend = useMemo(() => ({ Available: "bg-emerald-200", Partial: "bg-amber-200", Missing: "bg-rose-200" }), []);
  const inventoryRows = useMemo(
    () => [...uploadedFiles, ...(query.data?.inventory ?? [])],
    [query.data?.inventory, uploadedFiles]
  );

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(storageKey) ?? window.localStorage.getItem("tam-uploaded-files");
      if (!raw) return;
      const parsed = JSON.parse(raw) as z.infer<typeof FileInventorySchema>[];
      setUploadedFiles(parsed);
    } catch {
      setUploadedFiles([]);
    }
  }, [storageKey]);

  useEffect(() => {
    window.localStorage.setItem(storageKey, JSON.stringify(uploadedFiles));
  }, [uploadedFiles, storageKey]);

  useEffect(() => {
    if (!highlightedFile || inventoryRows.length === 0) return;
    const normalized = highlightedFile.trim().toLowerCase();
    const matched = inventoryRows.find((row) => row.file.trim().toLowerCase() === normalized);
    if (!matched) return;

    setHighlightedRowId(matched.id);
    setSelectedFile(matched);

    const scrollTimer = window.setTimeout(() => {
      const node = document.querySelector(`[data-rowid="${matched.id}"]`);
      if (node instanceof HTMLElement) {
        node.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }, 180);

    const clearTimer = window.setTimeout(() => setHighlightedRowId(null), 2400);
    return () => {
      window.clearTimeout(scrollTimer);
      window.clearTimeout(clearTimer);
    };
  }, [highlightedFile, inventoryRows]);

  useEffect(() => {
    if (!focusedCoverageSchedule || !focusedCoverageMonth || !query.data) return;
    const schedule = query.data.coverage.find((row) => row.schedule.toLowerCase() === focusedCoverageSchedule.toLowerCase());
    if (!schedule) return;
    const month = schedule.months.find((m) => m.month.toLowerCase() === focusedCoverageMonth.toLowerCase());
    if (!month) return;

    const key = makeCoverageKey(schedule.schedule, month.month);
    setHighlightedCoverageKey(key);

    const scrollTimer = window.setTimeout(() => {
      const node = document.querySelector(`[data-coverage-key="${key}"]`);
      if (node instanceof HTMLElement) {
        node.scrollIntoView({ behavior: "smooth", block: "center", inline: "center" });
      }
    }, 180);

    const clearTimer = window.setTimeout(() => setHighlightedCoverageKey(null), 2200);
    return () => {
      window.clearTimeout(scrollTimer);
      window.clearTimeout(clearTimer);
    };
  }, [focusedCoverageMonth, focusedCoverageSchedule, query.data]);

  if (query.isLoading || !query.data) return <div className="grid gap-4"><div className="h-72 animate-pulse rounded-lg bg-muted" /><div className="h-72 animate-pulse rounded-lg bg-muted" /></div>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between"><h2 className="text-xl font-semibold">Documents</h2><p className="text-xs text-muted-foreground">Last updated: {formatDateTime(query.data.lastUpdated)}</p></div>

      <DocumentUploadTool
        entityName={deal}
        onFilesProcessed={(rows) =>
          setUploadedFiles((prev) => {
            const merged = [...rows, ...prev];
            const uniqueByName = merged.filter((row, idx, arr) => arr.findIndex((x) => x.file === row.file) === idx);
            return uniqueByName;
          })
        }
      />

      <Card>
        <CardHeader><CardTitle>Coverage heatmap</CardTitle></CardHeader>
        <CardContent>
          <div className="mb-3 flex gap-3 text-xs">
            <span className="inline-flex items-center gap-1"><span className={`h-3 w-3 rounded ${legend.Available}`} /> Available</span>
            <span className="inline-flex items-center gap-1"><span className={`h-3 w-3 rounded ${legend.Partial}`} /> Partial</span>
            <span className="inline-flex items-center gap-1"><span className={`h-3 w-3 rounded ${legend.Missing}`} /> Missing</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr><th className="px-2 py-2 text-left">Schedule</th>{query.data.coverage[0]?.months.map((m) => <th key={m.month} className="px-2 py-2">{m.month}</th>)}</tr>
              </thead>
              <tbody>
                {query.data.coverage.map((row) => (
                  <tr key={row.schedule} className="border-t">
                    <td className="px-2 py-2 font-medium">{row.schedule}</td>
                    {row.months.map((cell) => (
                      <td key={cell.month} className="px-2 py-2">
                        <div
                          data-coverage-key={makeCoverageKey(row.schedule, cell.month)}
                          className={`mx-auto h-4 w-6 rounded ${legend[cell.status]} ${
                            highlightedCoverageKey && highlightedCoverageKey === makeCoverageKey(row.schedule, cell.month)
                              ? "ring-2 ring-cyan-500 ring-offset-2 ring-offset-background transition-all duration-300"
                              : ""
                          }`}
                        />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <DataTable
        title="File inventory"
        rows={inventoryRows}
        onRowClick={(row) => setSelectedFile(row)}
        rowClassName={(row) => {
          if (selectedFile?.id === row.id) return "tam-row-active";
          if (highlightedRowId && row.id === highlightedRowId) return "tam-source-highlight";
          return "";
        }}
        columns={[
          { key: "file", header: "File", render: (r) => <span className={r.file === highlightedFile ? "font-semibold text-primary" : ""}>{r.file}</span> },
          { key: "detectedType", header: "Detected Type" },
          { key: "periodCoverage", header: "Period Coverage" },
          { key: "entity", header: "Entity" },
          { key: "status", header: "Status" },
          { key: "confidence", header: "Confidence", render: (r) => `${Math.round(r.confidence * 100)}%` },
        ]}
      />

      <Card>
        <CardHeader><CardTitle>Missing / PBC suggestions</CardTitle></CardHeader>
        <CardContent className="space-y-2">
          {query.data.pbc.map((pbc) => (
            <div key={pbc.id} className="flex flex-wrap items-center justify-between gap-2 rounded border bg-card p-3">
              <div>
                <p className="font-medium">{pbc.request}</p>
                <p className="text-xs text-muted-foreground">Owner: {pbc.owner}</p>
              </div>
              <div className="flex items-center gap-2">
                <SeverityBadge severity={pbc.severity} />
                <Button size="sm" variant="outline" onClick={() => router.push(`/inquiry?prefill=${encodeURIComponent(pbc.request)}`)}>Create inquiry</Button>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      <Sheet open={!!selectedFile} onOpenChange={(v) => !v && setSelectedFile(null)}>
        <SheetContent
          side="right"
          className="w-[420px] overflow-hidden rounded-l-[34px] border-l border-slate-300/60 bg-gradient-to-b from-slate-100 to-slate-200 shadow-[-20px_0_46px_rgba(15,23,42,0.2)] dark:border-cyan-400/30 dark:from-slate-900 dark:to-slate-950 dark:shadow-[-22px_0_52px_rgba(34,211,238,0.18)]"
        >
          {selectedFile ? (
            <div className="relative space-y-3">
              <button
                type="button"
                aria-label="Close preview"
                onClick={() => setSelectedFile(null)}
                className="absolute right-0 top-0 rounded-full border border-border bg-card/85 p-1.5 text-muted-foreground transition hover:bg-muted hover:text-foreground"
              >
                <X className="h-4 w-4" />
              </button>
              <div className="pointer-events-none absolute -left-12 top-10 h-44 w-44 rounded-full bg-sky-200/18 blur-3xl dark:bg-cyan-400/20" />
              <div className="pointer-events-none absolute -left-6 bottom-20 h-36 w-36 rounded-full bg-emerald-200/14 blur-3xl dark:bg-emerald-400/12" />
              <h3 className="text-lg font-semibold">File Preview</h3>
              <p className="text-sm"><span className="font-semibold">File:</span> {selectedFile.file}</p>
              <p className="text-sm"><span className="font-semibold">Type:</span> {selectedFile.detectedType}</p>
              <p className="text-sm"><span className="font-semibold">Coverage:</span> {selectedFile.periodCoverage}</p>
              <div className="relative rounded-2xl border border-cyan-300/55 bg-cyan-100/40 p-3 text-sm shadow-[0_10px_25px_rgba(14,165,233,0.15)] dark:border-cyan-400/45 dark:bg-cyan-500/14 dark:shadow-[0_12px_30px_rgba(34,211,238,0.18)]">
                Mock preview pane for parsed sheet structure and detected mappings.
              </div>
            </div>
          ) : null}
        </SheetContent>
      </Sheet>
    </div>
  );
}
