"use client";

import { useCallback, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Upload, FileText, CheckCircle2, AlertCircle, Loader2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils/cn";
import { createDeal, uploadFiles, processDeal, getDealStatus, type Deal } from "@/lib/api/fdd-client";
import { useGlobalStore } from "@/lib/store/use-global-store";

type Stage = "form" | "uploading" | "processing" | "done" | "error";

const POLL_INTERVAL_MS = 2500;
const ALLOWED_EXTENSIONS = [".csv", ".xlsx", ".pdf", ".zip"];

function StageProgress({ stages }: { stages: Deal["stages"] }) {
  const order = [
    "ingestion", "coa_mapping", "financial_builder", "qoe_engine", "redflag_detector",
    "nwc_analyzer", "dcf_engine", "net_debt_bridge",
  ];
  const labels: Record<string, string> = {
    ingestion: "Ingesting data room",
    coa_mapping: "Mapping chart of accounts",
    financial_builder: "Building financial statements",
    qoe_engine: "Running QoE analysis",
    redflag_detector: "Detecting red flags",
    nwc_analyzer: "Analyzing net working capital",
    dcf_engine: "Running DCF valuation",
    net_debt_bridge: "Building net debt bridge",
  };
  return (
    <div className="space-y-2">
      {order.map((key) => {
        const status = stages[key as keyof typeof stages];
        return (
          <div key={key} className="flex items-center gap-3">
            {status === "complete" ? (
              <CheckCircle2 className="h-4 w-4 shrink-0 text-green-500" />
            ) : status === "running" ? (
              <Loader2 className="h-4 w-4 shrink-0 animate-spin text-primary" />
            ) : status === "failed" ? (
              <AlertCircle className="h-4 w-4 shrink-0 text-destructive" />
            ) : (
              <div className="h-4 w-4 shrink-0 rounded-full border-2 border-muted-foreground/30" />
            )}
            <span className={cn("text-sm", status === "complete" && "text-muted-foreground line-through", status === "running" && "font-medium")}>
              {labels[key]}
            </span>
          </div>
        );
      })}
    </div>
  );
}

export default function UploadPage() {
  const router = useRouter();
  const { setActiveDeal } = useGlobalStore();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [companyName, setCompanyName] = useState("");
  const [dealName, setDealName] = useState("");
  const [currency, setCurrency] = useState("USD");
  const [files, setFiles] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);
  const [stage, setStage] = useState<Stage>("form");
  const [deal, setDeal] = useState<Deal | null>(null);
  const [errorMsg, setErrorMsg] = useState("");

  const addFiles = (incoming: FileList | null) => {
    if (!incoming) return;
    const valid = Array.from(incoming).filter((f) =>
      ALLOWED_EXTENSIONS.some((ext) => f.name.toLowerCase().endsWith(ext))
    );
    setFiles((prev) => {
      const names = new Set(prev.map((f) => f.name));
      return [...prev, ...valid.filter((f) => !names.has(f.name))];
    });
  };

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    addFiles(e.dataTransfer.files);
  }, []);

  const submit = async () => {
    if (!companyName.trim() || !dealName.trim() || files.length === 0) return;
    setStage("uploading");
    setErrorMsg("");

    try {
      const created = await createDeal(companyName.trim(), dealName.trim(), currency);
      await uploadFiles(created.deal_id, files);
      setStage("processing");

      await processDeal(created.deal_id);

      // Poll until complete or failed
      let current = created;
      for (let i = 0; i < 120; i++) {
        await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
        current = await getDealStatus(created.deal_id);
        setDeal(current);
        const statuses = Object.values(current.stages);
        if (statuses.every((s) => s === "complete")) break;
        if (statuses.some((s) => s === "failed")) {
          throw new Error(current.error ?? "A processing stage failed.");
        }
      }

      setActiveDeal(`${current.company_name} — ${current.deal_name}`, current.deal_id);
      setStage("done");
      setDeal(current);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : String(err));
      setStage("error");
    }
  };

  if (stage === "processing" || stage === "uploading") {
    return (
      <div className="mx-auto max-w-xl py-12">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Loader2 className="h-5 w-5 animate-spin text-primary" />
              {stage === "uploading" ? "Uploading files…" : "Processing deal data…"}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            {deal && (
              <>
                <p className="text-sm text-muted-foreground">
                  {deal.company_name} — {deal.deal_name} &nbsp;·&nbsp; {deal.progress_pct}% complete
                </p>
                <StageProgress stages={deal.stages} />
              </>
            )}
            {stage === "uploading" && (
              <p className="text-sm text-muted-foreground">Uploading {files.length} file(s)…</p>
            )}
          </CardContent>
        </Card>
      </div>
    );
  }

  if (stage === "done" && deal) {
    return (
      <div className="mx-auto max-w-xl py-12">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-green-500">
              <CheckCircle2 className="h-5 w-5" />
              Analysis Complete
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            <p className="text-sm text-muted-foreground">
              <strong>{deal.company_name} — {deal.deal_name}</strong> has been fully processed
              and is now active in your workspace.
            </p>
            <StageProgress stages={deal.stages} />
            <div className="flex gap-3 pt-2">
              <Button onClick={() => router.push("/financial-analysis")} className="flex-1">
                View Financial Analysis
              </Button>
              <Button variant="outline" onClick={() => router.push("/risk-assessment")} className="flex-1">
                View Red Flags
              </Button>
            </div>
            <Button variant="ghost" size="sm" className="w-full" onClick={() => {
              setStage("form"); setFiles([]); setCompanyName(""); setDealName(""); setDeal(null);
            }}>
              Upload Another Deal
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (stage === "error") {
    return (
      <div className="mx-auto max-w-xl py-12">
        <Card className="border-destructive">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-destructive">
              <AlertCircle className="h-5 w-5" /> Processing Failed
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">{errorMsg}</p>
            <Button onClick={() => setStage("form")} variant="outline">Try Again</Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6 py-8">
      <div>
        <h1 className="text-2xl font-semibold">New Deal Analysis</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Upload a general ledger CSV or Excel export. The engine will map accounts, build
          financial statements, run QoE analysis, and detect red flags automatically.
        </p>
      </div>

      {/* Deal details */}
      <Card>
        <CardHeader><CardTitle className="text-base">Deal Information</CardTitle></CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-3">
          <div className="sm:col-span-1 space-y-1">
            <label className="text-xs font-medium text-muted-foreground">Company Name</label>
            <input
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              placeholder="Acme Manufacturing Co."
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
            />
          </div>
          <div className="sm:col-span-1 space-y-1">
            <label className="text-xs font-medium text-muted-foreground">Deal / Project Name</label>
            <input
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              placeholder="Project Falcon"
              value={dealName}
              onChange={(e) => setDealName(e.target.value)}
            />
          </div>
          <div className="sm:col-span-1 space-y-1">
            <label className="text-xs font-medium text-muted-foreground">Currency</label>
            <select
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
              value={currency}
              onChange={(e) => setCurrency(e.target.value)}
            >
              <option>USD</option><option>GBP</option><option>EUR</option><option>AUD</option><option>CAD</option>
            </select>
          </div>
        </CardContent>
      </Card>

      {/* File drop zone */}
      <Card>
        <CardHeader><CardTitle className="text-base">Upload GL / Financial Data</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            onClick={() => fileInputRef.current?.click()}
            className={cn(
              "flex cursor-pointer flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed p-10 transition-colors",
              dragging ? "border-primary bg-primary/5" : "border-border hover:border-primary/50 hover:bg-muted/30"
            )}
          >
            <Upload className="h-8 w-8 text-muted-foreground" />
            <div className="text-center">
              <p className="text-sm font-medium">Drop files here or click to browse</p>
              <p className="text-xs text-muted-foreground mt-1">CSV, Excel (.xlsx / .xls), or PDF · max 50 MB each</p>
            </div>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept=".csv,.xlsx,.xls,.pdf"
              className="hidden"
              onChange={(e) => addFiles(e.target.files)}
            />
          </div>

          {files.length > 0 && (
            <div className="space-y-2">
              {files.map((f) => (
                <div key={f.name} className="flex items-center gap-3 rounded-md border border-border bg-card px-3 py-2">
                  <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                  <span className="flex-1 truncate text-sm">{f.name}</span>
                  <span className="text-xs text-muted-foreground">{(f.size / 1024).toFixed(0)} KB</span>
                  <button onClick={() => setFiles((prev) => prev.filter((x) => x.name !== f.name))}>
                    <X className="h-4 w-4 text-muted-foreground hover:text-foreground" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Button
        className="w-full"
        size="lg"
        disabled={!companyName.trim() || !dealName.trim() || files.length === 0}
        onClick={submit}
      >
        Run Full Analysis
      </Button>
    </div>
  );
}
