"use client";

import { useEffect, useState } from "react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  Cell,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { AlertCircle, ChevronDown, ChevronRight, TrendingUp } from "lucide-react";
import { getQoE, getAdjustmentSource, type QoEReport, type QoEAdjustment } from "@/lib/api/fdd-client";
import { cn } from "@/lib/utils/cn";

const fmt = (v: string | number) =>
  `$${Math.abs(Number(v)).toLocaleString("en-US", { maximumFractionDigits: 0 })}`;

const fmtSigned = (v: string | number) => {
  const n = Number(v);
  return `${n >= 0 ? "+" : "−"}$${Math.abs(n).toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
};

// ─── Waterfall chart ──────────────────────────────────────────────────────────

function WaterfallChart({ report }: { report: QoEReport }) {
  const bars = report.waterfall.map((item, i) => {
    const val = Number(item.amount);
    const isBase = item.type === "base";
    const isResult = item.type === "result";
    // For bridge bars, we need start + delta for a "floating bar" effect
    const base = report.waterfall
      .slice(0, i)
      .filter((w) => w.type !== "result")
      .reduce((sum, w) => (w.type === "base" ? Number(w.amount) : sum + Number(w.amount)), 0);

    return {
      name: item.label.length > 28 ? item.label.slice(0, 26) + "…" : item.label,
      fullLabel: item.label,
      type: item.type,
      value: isBase || isResult ? val : Math.abs(val),
      base: isBase || isResult ? 0 : Math.min(base, base + val),
      fill:
        isBase ? "#6366f1" :
        isResult ? "#22c55e" :
        item.type === "addback" ? "#22c55e" : "#ef4444",
    };
  });

  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={bars} margin={{ top: 10, right: 10, left: 10, bottom: 60 }}>
        <XAxis
          dataKey="name"
          tick={{ fontSize: 11 }}
          angle={-35}
          textAnchor="end"
          interval={0}
        />
        <YAxis
          tickFormatter={(v) => `$${(v / 1_000).toFixed(0)}K`}
          tick={{ fontSize: 11 }}
          width={65}
        />
        <Tooltip
          formatter={(v: number, _name: string, props) => [fmt(v), props.payload.fullLabel]}
          labelFormatter={() => ""}
        />
        <ReferenceLine y={0} stroke="#666" />
        {/* Transparent base bar for floating effect */}
        <Bar dataKey="base" stackId="a" fill="transparent" />
        <Bar dataKey="value" stackId="a" radius={[3, 3, 0, 0]}>
          {bars.map((b, i) => (
            <Cell key={i} fill={b.fill} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

// ─── Adjustment ledger row ────────────────────────────────────────────────────

function AdjustmentRow({ adj, dealId }: { adj: QoEAdjustment; dealId: string }) {
  const [expanded, setExpanded] = useState(false);
  const [sourceLines, setSourceLines] = useState<unknown[] | null>(null);
  const [loading, setLoading] = useState(false);

  const loadSource = async () => {
    if (sourceLines !== null) return;
    setLoading(true);
    try {
      const data = await getAdjustmentSource(dealId, adj.adjustment_id);
      setSourceLines(data.gl_lines as unknown[]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="border-b border-border last:border-0">
      <button
        className="flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-muted/40 transition-colors"
        onClick={() => { setExpanded((p) => !p); if (!expanded) loadSource(); }}
      >
        {expanded ? <ChevronDown className="mt-0.5 h-4 w-4 shrink-0" /> : <ChevronRight className="mt-0.5 h-4 w-4 shrink-0" />}
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium truncate">{adj.label}</span>
            <Badge className={cn("text-xs", adj.direction === "add_back" ? "bg-green-500/15 text-green-600" : "bg-red-500/15 text-red-600")}>
              {adj.direction === "add_back" ? "Add-back" : "Deduction"}
            </Badge>
            <Badge className="text-xs border border-border bg-transparent text-foreground">{adj.category}</Badge>
            {adj.llm_reviewed && <Badge className="text-xs bg-purple-500/15 text-purple-600">LLM reviewed</Badge>}
          </div>
          <div className="mt-1 flex flex-wrap gap-4 text-xs text-muted-foreground">
            <span>{adj.period}</span>
            <span>Reported: {fmt(adj.reported_amount)}</span>
            <span className="font-medium text-green-600">Add-back: {fmt(adj.adjustment_amount)}</span>
            <span>{adj.rule_triggered ?? "manual"}</span>
          </div>
        </div>
      </button>
      {expanded && (
        <div className="mx-4 mb-3 rounded-md bg-muted/40 p-3 text-xs space-y-2">
          {adj.llm_reasoning && (
            <p className="text-muted-foreground italic">&quot;{adj.llm_reasoning}&quot;</p>
          )}
          <p className="text-muted-foreground">{adj.source_gl_line_ids.length} source GL line(s)</p>
          {loading && <Skeleton className="h-6 w-full" />}
          {sourceLines && sourceLines.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b text-muted-foreground">
                    <th className="pb-1 pr-4">Account</th>
                    <th className="pb-1 pr-4">Description</th>
                    <th className="pb-1 text-right">Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {(sourceLines as Record<string, unknown>[]).map((l, i) => (
                    <tr key={i} className="border-b border-border/50 last:border-0">
                      <td className="py-1 pr-4 font-mono">{String(l.account_code)}</td>
                      <td className="py-1 pr-4 text-muted-foreground truncate max-w-[200px]">{String(l.account_description)}</td>
                      <td className="py-1 text-right">{fmt(String(l.amount))}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export function QoeCenter({ dealId }: { dealId: string }) {
  const [report, setReport] = useState<QoEReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    getQoE(dealId)
      .then(setReport)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [dealId]);

  if (loading) return (
    <div className="space-y-4">
      <Skeleton className="h-48 w-full" />
      <Skeleton className="h-64 w-full" />
    </div>
  );

  if (error) return (
    <Card className="border-destructive">
      <CardContent className="flex items-center gap-3 py-6 text-destructive">
        <AlertCircle className="h-5 w-5 shrink-0" />
        <span className="text-sm">{error}</span>
      </CardContent>
    </Card>
  );

  if (!report) return null;

  return (
    <div className="space-y-6">
      {/* KPI banner */}
      <div className="grid gap-4 sm:grid-cols-3">
        <Card>
          <CardContent className="pt-5">
            <p className="text-xs text-muted-foreground uppercase tracking-wide">LTM Reported EBITDA</p>
            <p className="mt-1 text-2xl font-bold">{fmt(report.ltm_reported)}</p>
          </CardContent>
        </Card>
        <Card className="border-green-500/30 bg-green-500/5">
          <CardContent className="pt-5">
            <p className="text-xs text-muted-foreground uppercase tracking-wide">LTM Adjusted EBITDA</p>
            <p className="mt-1 text-2xl font-bold text-green-600">{fmt(report.ltm_adjusted)}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-5 flex items-start gap-3">
            <TrendingUp className="mt-1 h-5 w-5 shrink-0 text-green-500" />
            <div>
              <p className="text-xs text-muted-foreground uppercase tracking-wide">Total Add-backs (LTM)</p>
              <p className="mt-1 text-2xl font-bold">{fmtSigned(report.ltm_adjustment_total)}</p>
              <p className="text-xs text-muted-foreground">{report.adjustment_count} adjustments across {report.categories_adjusted.length} categories</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Waterfall */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold">EBITDA Bridge — Reported to Adjusted (LTM)</CardTitle>
        </CardHeader>
        <CardContent>
          <WaterfallChart report={report} />
        </CardContent>
      </Card>

      {/* Adjustment ledger */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold">
            Adjustment Ledger &nbsp;
            <span className="font-normal text-muted-foreground">({report.adjustments.length} items — click to expand GL audit trail)</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {report.adjustments.map((adj) => (
            <AdjustmentRow key={adj.adjustment_id} adj={adj} dealId={dealId} />
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
