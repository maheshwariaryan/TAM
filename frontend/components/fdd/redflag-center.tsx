"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, AlertCircle, Info, ChevronDown, ChevronRight, Shield } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { getRedFlags, type RedFlag, type RedFlagReport } from "@/lib/api/fdd-client";
import { cn } from "@/lib/utils/cn";

const SEVERITY_CONFIG = {
  High:          { icon: AlertCircle,   color: "text-red-500",    bg: "bg-red-500/10 border-red-500/30",    badge: "bg-red-500/15 text-red-600" },
  Medium:        { icon: AlertTriangle, color: "text-amber-500",  bg: "bg-amber-500/10 border-amber-500/30", badge: "bg-amber-500/15 text-amber-600" },
  Low:           { icon: Info,          color: "text-blue-500",   bg: "bg-blue-500/10 border-blue-500/30",  badge: "bg-blue-500/15 text-blue-600" },
  Informational: { icon: Info,          color: "text-slate-400",  bg: "",                                    badge: "bg-slate-500/15 text-slate-500" },
} as const;

const fmt = (v: string | number | null) =>
  v !== null ? `$${Math.abs(Number(v)).toLocaleString("en-US", { maximumFractionDigits: 0 })}` : null;

function SummaryChips({ summary }: { summary: RedFlagReport["summary"] }) {
  return (
    <div className="flex flex-wrap gap-3">
      {(["High", "Medium", "Low", "Informational"] as const).map((sev) => {
        const count = summary[sev.toLowerCase() as keyof typeof summary] as number;
        const cfg = SEVERITY_CONFIG[sev];
        return (
          <div key={sev} className={cn("flex items-center gap-2 rounded-lg border px-4 py-2.5", cfg.bg)}>
            <cfg.icon className={cn("h-4 w-4", cfg.color)} />
            <span className="text-sm font-semibold">{count}</span>
            <span className="text-sm text-muted-foreground">{sev}</span>
          </div>
        );
      })}
      <div className="flex items-center gap-2 rounded-lg border px-4 py-2.5">
        <Shield className="h-4 w-4 text-muted-foreground" />
        <span className="text-sm font-semibold">{summary.total}</span>
        <span className="text-sm text-muted-foreground">Total</span>
      </div>
    </div>
  );
}

function FlagRow({ flag }: { flag: RedFlag }) {
  const [expanded, setExpanded] = useState(false);
  const cfg = SEVERITY_CONFIG[flag.severity];
  const impactLow = fmt(flag.financial_impact_low);
  const impactHigh = fmt(flag.financial_impact_high);

  return (
    <div className={cn("rounded-lg border transition-colors", expanded ? cfg.bg : "hover:bg-muted/30")}>
      <button
        className="flex w-full items-start gap-4 p-4 text-left"
        onClick={() => setExpanded((p) => !p)}
      >
        <cfg.icon className={cn("mt-0.5 h-5 w-5 shrink-0", cfg.color)} />
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <Badge className={cn("text-xs font-semibold", cfg.badge)}>{flag.severity}</Badge>
            <Badge className="text-xs border border-border bg-transparent text-foreground">{flag.category}</Badge>
            {flag.rule_id && <span className="text-xs text-muted-foreground font-mono">{flag.rule_id}</span>}
          </div>
          <p className="mt-1 text-sm font-semibold">{flag.title}</p>
          <p className="mt-0.5 text-xs text-muted-foreground line-clamp-2">{flag.description}</p>
        </div>
        <div className="shrink-0 text-right hidden sm:block">
          {impactLow && impactHigh && (
            <p className="text-xs text-muted-foreground">
              {impactLow} – {impactHigh}
              <br /><span className="text-[10px]">est. impact</span>
            </p>
          )}
        </div>
        {expanded ? <ChevronDown className="mt-0.5 h-4 w-4 shrink-0" /> : <ChevronRight className="mt-0.5 h-4 w-4 shrink-0" />}
      </button>

      {expanded && (
        <div className="px-4 pb-4 space-y-4">
          <p className="text-sm text-muted-foreground">{flag.description}</p>

          {flag.llm_context && (
            <div className="rounded-md bg-muted/60 p-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1">Analysis</p>
              <p className="text-sm">{flag.llm_context}</p>
            </div>
          )}

          {flag.diligence_questions.length > 0 && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">Diligence Questions</p>
              <ol className="space-y-1.5">
                {flag.diligence_questions.map((q, i) => (
                  <li key={i} className="flex gap-2 text-sm">
                    <span className="shrink-0 font-semibold text-primary">{i + 1}.</span>
                    <span>{q}</span>
                  </li>
                ))}
              </ol>
            </div>
          )}

          {flag.affected_periods.length > 0 && (
            <div className="flex flex-wrap gap-1">
              <span className="text-xs text-muted-foreground mr-1">Periods:</span>
              {flag.affected_periods.slice(0, 12).map((p) => (
                <Badge key={p} className="text-xs px-1.5 py-0 border border-border bg-transparent text-foreground">{p}</Badge>
              ))}
              {flag.affected_periods.length > 12 && (
                <span className="text-xs text-muted-foreground">+{flag.affected_periods.length - 12} more</span>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function RedFlagCenter({ dealId }: { dealId: string }) {
  const [report, setReport] = useState<RedFlagReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>("All");

  useEffect(() => {
    setLoading(true);
    setError(null);
    getRedFlags(dealId)
      .then(setReport)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [dealId]);

  if (loading) return (
    <div className="space-y-3">
      {[1, 2, 3].map((i) => <Skeleton key={i} className="h-20 w-full" />)}
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

  const severities = ["All", "High", "Medium", "Low", "Informational"];
  const visible = filter === "All"
    ? report.flags
    : report.flags.filter((f) => f.severity === filter);

  return (
    <div className="space-y-6">
      <SummaryChips summary={report.summary} />

      {/* Severity filter */}
      <div className="flex flex-wrap gap-2">
        {severities.map((s) => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            className={cn(
              "rounded-full border px-3 py-1 text-xs font-medium transition-colors",
              filter === s ? "bg-primary text-primary-foreground border-primary" : "hover:bg-muted"
            )}
          >
            {s}
          </button>
        ))}
      </div>

      {/* Flag list */}
      <div className="space-y-3">
        {visible.length === 0 && (
          <p className="text-sm text-muted-foreground py-8 text-center">No flags at this severity level.</p>
        )}
        {visible.map((flag) => (
          <FlagRow key={flag.flag_id} flag={flag} />
        ))}
      </div>
    </div>
  );
}
