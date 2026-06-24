"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { DataTable } from "@/components/tables/data-table";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import type { DecisionQueueItem, Inquiry } from "@/lib/schemas/types";
import { useGlobalStore } from "@/lib/store/use-global-store";
import { useApiQuery } from "@/hooks/use-api-query";
import { DecisionQueueResponseSchema, InquiryResponseSchema } from "@/lib/schemas/types";

export default function InquiryPage() {
  return (
    <Suspense fallback={<div className="h-80 animate-pulse rounded-lg bg-muted" />}>
      <InquiryPageContent />
    </Suspense>
  );
}

function InquiryPageContent() {
  const router = useRouter();
  const params = useSearchParams();
  const { deal, period, basis } = useGlobalStore();
  const query = useApiQuery(
    ["inquiry", deal, period, basis],
    `/api/deal/inquiry?deal=${encodeURIComponent(deal)}&period=${encodeURIComponent(period)}&basis=${encodeURIComponent(basis)}`,
    InquiryResponseSchema
  );
  const decisionQueueQuery = useApiQuery(
    ["decision-queue-inquiry", deal, period, basis],
    `/api/deal/decision-queue?deal=${encodeURIComponent(deal)}&period=${encodeURIComponent(period)}&basis=${encodeURIComponent(basis)}`,
    DecisionQueueResponseSchema
  );
  const [selected, setSelected] = useState<Inquiry | null>(null);
  const [selectedQueueItem, setSelectedQueueItem] = useState<DecisionQueueItem | null>(null);
  const [queueStatusOverrides, setQueueStatusOverrides] = useState<Record<string, DecisionQueueItem["status"]>>({});
  const [highlightedInquiryId, setHighlightedInquiryId] = useState<string | null>(null);
  const queueStorageKey = `tam-decision-queue-status:${deal}`;

  const rows = useMemo(() => {
    if (!query.data) return [];
    const prefill = params.get("prefill");
    if (!prefill) return query.data.inquiries;
    const exists = query.data.inquiries.some((r) => r.request.toLowerCase().includes(prefill.toLowerCase()));
    if (exists) return query.data.inquiries;
    return [{ id: "INQ-NEW", request: prefill, owner: "Unassigned", dueDate: "2026-02-19", status: "Open", blocking: false }, ...query.data.inquiries];
  }, [params, query.data]);

  const decisionQueueRows = useMemo(() => {
    if (!decisionQueueQuery.data) return [];
    return decisionQueueQuery.data.items.map((item) => ({
      ...item,
      status: queueStatusOverrides[item.id] ?? item.status,
    }));
  }, [decisionQueueQuery.data, queueStatusOverrides]);

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(queueStorageKey);
      if (!raw) {
        setQueueStatusOverrides({});
        return;
      }
      setQueueStatusOverrides(JSON.parse(raw) as Record<string, DecisionQueueItem["status"]>);
    } catch {
      setQueueStatusOverrides({});
    }
  }, [queueStorageKey]);

  useEffect(() => {
    window.localStorage.setItem(queueStorageKey, JSON.stringify(queueStatusOverrides));
  }, [queueStatusOverrides, queueStorageKey]);

  useEffect(() => {
    const focusType = params.get("focus");
    const focusId = params.get("id");
    if (focusType !== "inquiry" || !focusId || !rows.length) return;
    const target = rows.find((row) => row.id.toLowerCase() === focusId.toLowerCase());
    if (!target) return;
    setHighlightedInquiryId(target.id);
    setSelected(target);

    const scrollTimer = window.setTimeout(() => {
      const node = document.querySelector(`[data-rowid="${target.id}"]`);
      if (node instanceof HTMLElement) {
        node.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }, 180);

    const clearTimer = window.setTimeout(() => setHighlightedInquiryId(null), 2200);
    return () => {
      window.clearTimeout(scrollTimer);
      window.clearTimeout(clearTimer);
    };
  }, [params, rows]);

  if (query.isLoading || !query.data) {
    return <div className="h-80 animate-pulse rounded-lg bg-muted" />;
  }

  return (
    <div className="space-y-5">
      <h2 className="text-xl font-semibold">Inquiry</h2>
      <DataTable
        rows={rows}
        onRowClick={(row) => setSelected(row)}
        rowClassName={(row) => (highlightedInquiryId && row.id === highlightedInquiryId ? "tam-source-highlight" : "")}
        columns={[
          { key: "id", header: "ID" },
          { key: "request", header: "Request" },
          { key: "owner", header: "Owner" },
          { key: "dueDate", header: "Due Date" },
          { key: "status", header: "Status" },
          { key: "blocking", header: "Blocking Yes/No", render: (r) => (r.blocking ? "Yes" : "No") },
        ]}
      />

      <div id="decision-queue">
        <DataTable
          title={`Decision Queue (${decisionQueueQuery.data?.readiness ?? "Draft"})`}
          rows={decisionQueueRows}
          onRowClick={(row) => setSelectedQueueItem(row)}
          columns={[
            { key: "title", header: "Action" },
            { key: "impactArea", header: "Impact Area" },
            { key: "impactScore", header: "Impact Score", render: (r) => r.impactScore.toFixed(1) },
            { key: "owner", header: "Owner" },
            { key: "dueDate", header: "Due Date" },
            {
              key: "status",
              header: "Status",
              render: (r) => (
                <span className={`rounded-full px-2 py-1 text-xs font-semibold ${
                  r.status === "Resolved"
                    ? "bg-emerald-100 text-emerald-700"
                    : r.status === "In Progress"
                      ? "bg-blue-100 text-blue-700"
                      : r.status === "Deferred"
                        ? "bg-slate-100 text-slate-700"
                        : "bg-amber-100 text-amber-700"
                }`}>
                  {r.status}
                </span>
              ),
            },
            {
              key: "blocking",
              header: "Blocking",
              render: (r) => (r.blocking ? "Yes" : "No"),
            },
            {
              key: "sourceLabel",
              header: "Source",
            },
          ]}
        />
      </div>

      <Sheet open={!!selected} onOpenChange={(v) => !v && setSelected(null)}>
        <SheetContent side="right" className="w-[460px]">
          {selected ? (
            <div className="space-y-3">
              <h3 className="text-lg font-semibold">{selected.id}</h3>
              <p className="text-sm">{selected.request}</p>
              <div className="rounded border bg-muted/30 p-3 text-sm">Discussion thread placeholder: analyst comments, seller responses, attachment links.</div>
              <div className="flex flex-wrap gap-2">
                <Button variant="outline" size="sm" onClick={() => router.push("/documents")}>Go to Documents</Button>
                <Button variant="outline" size="sm" onClick={() => router.push("/risk-assessment")}>Go to Risk Assessment</Button>
                <Button variant="outline" size="sm" onClick={() => router.push("/financial-analysis")}>Go to Financial Analysis</Button>
              </div>
            </div>
          ) : null}
        </SheetContent>
      </Sheet>

      <Sheet open={!!selectedQueueItem} onOpenChange={(v) => !v && setSelectedQueueItem(null)}>
        <SheetContent side="right" className="w-[500px]">
          {selectedQueueItem ? (
            <div className="space-y-3">
              <h3 className="text-lg font-semibold">{selectedQueueItem.title}</h3>
              <p className="text-sm text-muted-foreground">{selectedQueueItem.rationale}</p>
              <div className="grid gap-2 text-sm">
                <p><span className="font-semibold">Impact Area:</span> {selectedQueueItem.impactArea}</p>
                <p><span className="font-semibold">Impact Score:</span> {selectedQueueItem.impactScore.toFixed(1)}</p>
                <p><span className="font-semibold">Owner:</span> {selectedQueueItem.owner}</p>
                <p><span className="font-semibold">Due Date:</span> {selectedQueueItem.dueDate}</p>
                <p><span className="font-semibold">Blocking:</span> {selectedQueueItem.blocking ? "Yes" : "No"}</p>
                <p><span className="font-semibold">Source:</span> {selectedQueueItem.sourceLabel}</p>
              </div>
              <div className="flex flex-wrap gap-2">
                {(["Open", "In Progress", "Resolved", "Deferred"] as const).map((status) => (
                  <Button
                    key={status}
                    variant={status === (queueStatusOverrides[selectedQueueItem.id] ?? selectedQueueItem.status) ? "default" : "outline"}
                    size="sm"
                    onClick={() =>
                      setQueueStatusOverrides((prev) => ({
                        ...prev,
                        [selectedQueueItem.id]: status,
                      }))
                    }
                  >
                    Mark {status}
                  </Button>
                ))}
              </div>
              <Button onClick={() => router.push(selectedQueueItem.sourceUrl)}>Open Source Context</Button>
            </div>
          ) : null}
        </SheetContent>
      </Sheet>
    </div>
  );
}
