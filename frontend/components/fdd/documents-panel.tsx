"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { AlertCircle } from "lucide-react";
import { getDocumentInventory, type DocumentInventory } from "@/lib/api/fdd-client";

const parseStatusClass: Record<string, string> = {
  parsed: "bg-emerald-100 text-emerald-700",
  failed: "bg-rose-100 text-rose-700",
  skipped: "bg-amber-100 text-amber-700",
  pending: "bg-slate-100 text-slate-700",
};

export function DocumentsPanel({ dealId }: { dealId: string }) {
  const [data, setData] = useState<DocumentInventory | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    getDocumentInventory(dealId)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [dealId]);

  if (loading) return <Skeleton className="h-64 w-full" />;

  if (error) return (
    <Card className="border-destructive">
      <CardContent className="flex items-center gap-3 py-6 text-destructive">
        <AlertCircle className="h-5 w-5 shrink-0" />
        <span className="text-sm">{error}</span>
      </CardContent>
    </Card>
  );

  if (!data || data.documents.length === 0) {
    return (
      <Card className="border-dashed">
        <CardContent className="py-8 text-center text-sm text-muted-foreground">
          No documents ingested yet for this deal.
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader><CardTitle className="text-sm font-semibold">Document Inventory ({data.documents.length})</CardTitle></CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b text-xs text-muted-foreground">
                <th className="py-2 pr-4">File</th>
                <th className="py-2 pr-4">Detected Type</th>
                <th className="py-2 pr-4">Status</th>
                <th className="py-2 pr-4">Confidence</th>
                <th className="py-2">Size</th>
              </tr>
            </thead>
            <tbody>
              {data.documents.map((doc) => (
                <tr key={doc.filename} className="border-b border-border/50 last:border-0">
                  <td className="py-2 pr-4 font-medium">{doc.filename}</td>
                  <td className="py-2 pr-4">{doc.document_type.replace(/_/g, " ")}</td>
                  <td className="py-2 pr-4">
                    <span className={`rounded-full px-2 py-1 text-xs font-semibold ${parseStatusClass[doc.parse_status] ?? ""}`}>
                      {doc.parse_status}
                    </span>
                    {doc.parse_error && <p className="mt-1 text-xs text-rose-600">{doc.parse_error}</p>}
                  </td>
                  <td className="py-2 pr-4">{Math.round(doc.confidence * 100)}%</td>
                  <td className="py-2">{(doc.size_bytes / 1024).toFixed(0)} KB</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      {data.missing_recommended.length > 0 && (
        <Card>
          <CardHeader><CardTitle className="text-sm font-semibold">Missing Recommended Documents</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            {data.missing_recommended.map((item) => (
              <div key={item} className="flex items-center justify-between rounded border bg-card p-3 text-sm">
                <span>{item.replace(/_/g, " ")}</span>
                <Badge className="bg-amber-500/15 text-amber-600 text-xs">Not uploaded</Badge>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
