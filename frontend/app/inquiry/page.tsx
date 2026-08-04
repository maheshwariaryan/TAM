"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { DataTable } from "@/components/tables/data-table";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { useGlobalStore } from "@/lib/store/use-global-store";
import {
  createInquiry,
  deleteInquiry,
  getDecisionQueue,
  getInquiries,
  updateInquiry,
  type DecisionQueueItem,
  type DecisionQueueResponse,
  type InquiryItem,
  type InquiryStatus,
} from "@/lib/api/fdd-client";

const STATUS_OPTIONS: InquiryStatus[] = ["Open", "In Progress", "Resolved", "Deferred"];
const PREFILL_ID = "INQ-NEW";

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
  const { dealId } = useGlobalStore();

  const [inquiries, setInquiries] = useState<InquiryItem[]>([]);
  const [decisionQueue, setDecisionQueue] = useState<DecisionQueueResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<InquiryItem | null>(null);
  const [selectedQueueItem, setSelectedQueueItem] = useState<DecisionQueueItem | null>(null);
  const [queueStatusOverrides, setQueueStatusOverrides] = useState<Record<string, InquiryStatus>>({});
  const [highlightedInquiryId, setHighlightedInquiryId] = useState<string | null>(null);
  const queueStorageKey = `tam-decision-queue-status:${dealId ?? "none"}`;

  const refresh = useCallback(() => {
    if (!dealId) return;
    setLoading(true);
    setError(null);
    Promise.all([getInquiries(dealId), getDecisionQueue(dealId)])
      .then(([inq, dq]) => {
        setInquiries(inq);
        setDecisionQueue(dq);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load inquiry data."))
      .finally(() => setLoading(false));
  }, [dealId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const rows = useMemo(() => {
    const prefill = params.get("prefill");
    if (!prefill) return inquiries;
    const exists = inquiries.some((r) => r.request.toLowerCase().includes(prefill.toLowerCase()));
    if (exists) return inquiries;
    const draft: InquiryItem = {
      id: PREFILL_ID,
      deal_id: dealId ?? "",
      request: prefill,
      owner: "Unassigned",
      due_date: "Unscheduled",
      status: "Open",
      blocking: false,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    return [draft, ...inquiries];
  }, [params, inquiries, dealId]);

  const decisionQueueRows = useMemo(() => {
    if (!decisionQueue) return [];
    return decisionQueue.items.map((item) => ({
      ...item,
      status: queueStatusOverrides[item.id] ?? item.status,
    }));
  }, [decisionQueue, queueStatusOverrides]);

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(queueStorageKey);
      setQueueStatusOverrides(raw ? (JSON.parse(raw) as Record<string, InquiryStatus>) : {});
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

  const handleSaveDraft = async () => {
    if (!dealId || !selected || selected.id !== PREFILL_ID) return;
    const created = await createInquiry(dealId, {
      request: selected.request,
      owner: selected.owner,
      due_date: selected.due_date,
      status: selected.status,
      blocking: selected.blocking,
    });
    router.replace("/inquiry");
    setSelected(created);
    refresh();
  };

  const handleStatusChange = async (status: InquiryStatus) => {
    if (!dealId || !selected || selected.id === PREFILL_ID) return;
    const updated = await updateInquiry(dealId, selected.id, { status });
    setSelected(updated);
    refresh();
  };

  const handleDelete = async () => {
    if (!dealId || !selected || selected.id === PREFILL_ID) return;
    await deleteInquiry(dealId, selected.id);
    setSelected(null);
    refresh();
  };

  if (!dealId) {
    return (
      <div className="space-y-5">
        <h2 className="text-xl font-semibold">Inquiry</h2>
        <div className="rounded-md border px-3 py-2 text-sm text-muted-foreground">
          Select a deal to view its inquiry tracker and decision queue.
        </div>
      </div>
    );
  }

  if (loading && inquiries.length === 0) {
    return <div className="h-80 animate-pulse rounded-lg bg-muted" />;
  }

  return (
    <div className="space-y-5">
      <h2 className="text-xl font-semibold">Inquiry</h2>
      {error ? <p className="text-xs text-destructive">{error}</p> : null}
      <DataTable
        rows={rows}
        onRowClick={(row) => setSelected(row)}
        rowClassName={(row) => (highlightedInquiryId && row.id === highlightedInquiryId ? "tam-source-highlight" : "")}
        columns={[
          { key: "id", header: "ID" },
          { key: "request", header: "Request" },
          { key: "owner", header: "Owner" },
          { key: "due_date", header: "Due Date" },
          { key: "status", header: "Status" },
          { key: "blocking", header: "Blocking Yes/No", render: (r) => (r.blocking ? "Yes" : "No") },
        ]}
      />

      <div id="decision-queue">
        <DataTable
          title={`Decision Queue (${decisionQueue?.readiness ?? "Draft"})`}
          rows={decisionQueueRows}
          onRowClick={(row) => setSelectedQueueItem(row)}
          columns={[
            { key: "title", header: "Action" },
            { key: "impact_area", header: "Impact Area" },
            { key: "impact_score", header: "Impact Score", render: (r) => r.impact_score.toFixed(1) },
            { key: "owner", header: "Owner" },
            { key: "due_date", header: "Due Date" },
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
              key: "source_label",
              header: "Source",
            },
          ]}
        />
      </div>

      <Sheet open={!!selected} onOpenChange={(v) => !v && setSelected(null)}>
        <SheetContent side="right" className="w-[460px]">
          {selected ? (
            <div className="space-y-3">
              <h3 className="text-lg font-semibold">{selected.id === PREFILL_ID ? "New Inquiry" : selected.id}</h3>
              <p className="text-sm">{selected.request}</p>
              <div className="rounded border bg-muted/30 p-3 text-sm">Discussion thread placeholder: analyst comments, seller responses, attachment links.</div>

              {selected.id === PREFILL_ID ? (
                <Button size="sm" onClick={handleSaveDraft}>Save to Tracker</Button>
              ) : (
                <>
                  <div className="flex flex-wrap gap-2">
                    {STATUS_OPTIONS.map((status) => (
                      <Button
                        key={status}
                        variant={status === selected.status ? "default" : "outline"}
                        size="sm"
                        onClick={() => handleStatusChange(status)}
                      >
                        Mark {status}
                      </Button>
                    ))}
                  </div>
                  <Button variant="outline" size="sm" onClick={handleDelete}>Delete Inquiry</Button>
                </>
              )}

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
                <p><span className="font-semibold">Impact Area:</span> {selectedQueueItem.impact_area}</p>
                <p><span className="font-semibold">Impact Score:</span> {selectedQueueItem.impact_score.toFixed(1)}</p>
                <p><span className="font-semibold">Owner:</span> {selectedQueueItem.owner}</p>
                <p><span className="font-semibold">Due Date:</span> {selectedQueueItem.due_date}</p>
                <p><span className="font-semibold">Blocking:</span> {selectedQueueItem.blocking ? "Yes" : "No"}</p>
                <p><span className="font-semibold">Source:</span> {selectedQueueItem.source_label}</p>
              </div>
              <div className="flex flex-wrap gap-2">
                {STATUS_OPTIONS.map((status) => (
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
              <Button onClick={() => router.push(selectedQueueItem.source_url)}>Open Source Context</Button>
            </div>
          ) : null}
        </SheetContent>
      </Sheet>
    </div>
  );
}
