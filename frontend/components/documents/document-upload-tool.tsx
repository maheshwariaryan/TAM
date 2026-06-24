"use client";

import { useRef, useState } from "react";
import { UploadCloud, File as FileIcon } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { z } from "zod";
import { FileInventorySchema } from "@/lib/schemas/types";

type InventoryFile = z.infer<typeof FileInventorySchema>;

type UploadItem = {
  id: string;
  name: string;
  sizeLabel: string;
  progress: number;
  status: "Queued" | "Uploading" | "Processed";
};

function inferType(name: string) {
  const n = name.toLowerCase();
  if (n.includes("tb")) return "Trial Balance";
  if (n.includes("gl")) return "General Ledger";
  if (n.includes("ar")) return "AR Aging";
  if (n.includes("ap")) return "AP Aging";
  if (n.includes("bank")) return "Bank Statements";
  if (n.includes("payroll")) return "Payroll";
  if (n.endsWith(".csv")) return "General Ledger";
  if (n.endsWith(".pdf")) return "Bank Statements";
  return "Unclassified";
}

function formatSize(size: number) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function toInventoryRow(file: File, entityName?: string): InventoryFile {
  return {
    id: `UP-${Date.now()}-${Math.round(Math.random() * 10_000)}`,
    file: file.name,
    detectedType: inferType(file.name),
    periodCoverage: "Pending detection",
    entity: entityName?.trim() || "Uploaded Entity",
    status: "Processed",
    confidence: 0.86,
  };
}

export function DocumentUploadTool({
  onFilesProcessed,
  entityName,
}: {
  onFilesProcessed: (rows: InventoryFile[]) => void;
  entityName?: string;
}) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [uploads, setUploads] = useState<UploadItem[]>([]);
  const [dragActive, setDragActive] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const accepted = ".xlsx,.csv,.pdf,.zip";
  const acceptedExt = [".xlsx", ".csv", ".pdf", ".zip"];

  const runUpload = (files: File[]) => {
    if (!files.length) return;
    const valid = files.filter((file) => acceptedExt.some((ext) => file.name.toLowerCase().endsWith(ext)));
    const invalid = files.length - valid.length;
    if (invalid > 0) {
      setError(`${invalid} file(s) were skipped. Allowed types: .xlsx, .csv, .pdf, .zip`);
    } else {
      setError(null);
    }
    if (!valid.length) return;

    const queued: UploadItem[] = valid.map((file) => ({
      id: `${file.name}-${Date.now()}-${Math.round(Math.random() * 10_000)}`,
      name: file.name,
      sizeLabel: formatSize(file.size),
      progress: 0,
      status: "Queued",
    }));

    setUploads((prev) => [...queued, ...prev]);

    queued.forEach((upload, index) => {
      const tickEvery = 140 + index * 30;
      const interval = setInterval(() => {
        setUploads((prev) =>
          prev.map((item) => {
            if (item.id !== upload.id) return item;
            const next = Math.min(100, item.progress + 16);
            return {
              ...item,
              progress: next,
              status: next === 100 ? "Processed" : "Uploading",
            };
          })
        );
      }, tickEvery);

      setTimeout(() => {
        clearInterval(interval);
        setUploads((prev) =>
          prev.map((item) => (item.id === upload.id ? { ...item, progress: 100, status: "Processed" } : item))
        );
        const f = valid[index];
        if (f) onFilesProcessed([toInventoryRow(f, entityName)]);
      }, 900 + index * 240);
    });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Upload Documents</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div
          className={`rounded-lg border-2 border-dashed p-6 text-center transition ${dragActive ? "border-primary bg-primary/5" : "border-border bg-card"}`}
          onDragOver={(e) => {
            e.preventDefault();
            setDragActive(true);
          }}
          onDragLeave={() => setDragActive(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragActive(false);
            runUpload(Array.from(e.dataTransfer.files));
          }}
        >
          <UploadCloud className="mx-auto mb-2 h-8 w-8 text-muted-foreground" />
          <p className="text-sm font-medium">Drag and drop files here</p>
          <p className="text-xs text-muted-foreground">or choose files from your computer (.xlsx, .csv, .pdf, .zip)</p>
          <div className="mt-3">
            <Button variant="outline" size="sm" onClick={() => inputRef.current?.click()}>
              Select files
            </Button>
            <input
              ref={inputRef}
              type="file"
              className="hidden"
              accept={accepted}
              multiple
              onChange={(e) => runUpload(Array.from(e.target.files ?? []))}
            />
          </div>
        </div>

        {uploads.length > 0 ? (
          <div className="space-y-2">
            {uploads.slice(0, 6).map((item) => (
              <div key={item.id} className="rounded border bg-card p-3">
                <div className="mb-2 flex items-center justify-between gap-2 text-sm">
                  <span className="inline-flex items-center gap-2 font-medium"><FileIcon className="h-4 w-4" />{item.name}</span>
                  <span className="text-xs text-muted-foreground">{item.sizeLabel}</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-muted">
                  <div className="h-full bg-primary" style={{ width: `${item.progress}%` }} />
                </div>
                <p className="mt-1 text-xs text-muted-foreground">{item.status}</p>
              </div>
            ))}
          </div>
        ) : null}
        {error ? <p className="text-xs text-rose-600">{error}</p> : null}
      </CardContent>
    </Card>
  );
}
