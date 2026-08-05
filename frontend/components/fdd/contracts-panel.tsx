"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { AlertCircle, RefreshCw } from "lucide-react";
import { getContracts, analyzeContracts, type ContractAnalysisReport } from "@/lib/api/fdd-client";

const clauseLabels: Record<string, string> = {
  change_of_control: "Change of Control",
  prepayment: "Prepayment",
  event_of_default: "Event of Default",
  covenant: "Covenant",
  material_obligation: "Material Obligation",
};

export function ContractsPanel({ dealId }: { dealId: string }) {
  const [report, setReport] = useState<ContractAnalysisReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    setError(null);
    getContracts(dealId)
      .then(setReport)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(load, [dealId]);

  const handleAnalyze = async () => {
    setAnalyzing(true);
    try {
      const result = await analyzeContracts(dealId);
      setReport(result);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setAnalyzing(false);
    }
  };

  if (loading) return <Skeleton className="h-48 w-full" />;

  if (error && !report) return (
    <Card className="border-dashed">
      <CardContent className="flex flex-col items-center gap-2 py-8 text-center text-sm text-muted-foreground">
        <AlertCircle className="h-5 w-5" />
        <span>{error}</span>
        <Button size="sm" variant="outline" onClick={handleAnalyze} disabled={analyzing}>
          <RefreshCw className={`mr-1 h-3.5 w-3.5 ${analyzing ? "animate-spin" : ""}`} /> Analyze contracts
        </Button>
      </CardContent>
    </Card>
  );

  if (!report || report.status === "skipped") {
    return (
      <Card className="border-dashed">
        <CardContent className="flex flex-col items-center gap-3 py-8 text-center text-sm text-muted-foreground">
          <span>{report?.message ?? "No debt agreements uploaded."}</span>
          <Button size="sm" variant="outline" onClick={handleAnalyze} disabled={analyzing}>
            <RefreshCw className={`mr-1 h-3.5 w-3.5 ${analyzing ? "animate-spin" : ""}`} /> Re-analyze
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-sm font-semibold">Contract Instruments &amp; Clauses ({report.clauses.length})</CardTitle>
        <Button size="sm" variant="outline" onClick={handleAnalyze} disabled={analyzing}>
          <RefreshCw className={`mr-1 h-3.5 w-3.5 ${analyzing ? "animate-spin" : ""}`} /> Re-analyze
        </Button>
      </CardHeader>
      <CardContent className="space-y-3">
        {report.clauses.length === 0 && (
          <p className="text-sm text-muted-foreground">Instruments extracted, but no clause detail found in the source text.</p>
        )}
        {report.clauses.map((clause, i) => (
          <div key={i} className="rounded-lg border bg-card p-3 text-sm">
            <div className="mb-1 flex flex-wrap items-center gap-2">
              <Badge className="bg-primary/10 text-primary text-xs">{clauseLabels[clause.clause_type] ?? clause.clause_type}</Badge>
              <span className="text-xs text-muted-foreground">{clause.source_document}</span>
              <span className="text-xs text-muted-foreground">{Math.round(clause.confidence * 100)}% confidence</span>
            </div>
            <p className="text-muted-foreground">{clause.summary}</p>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
