"use client";

import { useEffect, useState } from "react";
import { TrendingUp, BarChart2, Percent, Scale, Landmark, ShieldAlert } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import {
  getFinancialSummary,
  getQoE,
  getNWC,
  getNetDebt,
  getRedFlags,
  type FinancialSummary,
  type QoEReport,
  type NWCReport,
  type NetDebtReport,
  type RedFlagReport,
} from "@/lib/api/fdd-client";

const fmt = (v: string | number | null | undefined) =>
  v === null || v === undefined ? "—" : `$${Math.abs(Number(v)).toLocaleString("en-US", { maximumFractionDigits: 0 })}`;

export function DealSummaryBanner({ dealId }: { dealId: string }) {
  const [financials, setFinancials] = useState<FinancialSummary | null>(null);
  const [qoe, setQoe] = useState<QoEReport | null>(null);
  const [nwc, setNwc] = useState<NWCReport | null>(null);
  const [netDebt, setNetDebt] = useState<NetDebtReport | null>(null);
  const [redflags, setRedflags] = useState<RedFlagReport | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.allSettled([
      getFinancialSummary(dealId),
      getQoE(dealId),
      getNWC(dealId),
      getNetDebt(dealId),
      getRedFlags(dealId),
    ]).then(([f, q, n, nd, rf]) => {
      setFinancials(f.status === "fulfilled" ? f.value : null);
      setQoe(q.status === "fulfilled" ? q.value : null);
      setNwc(n.status === "fulfilled" ? n.value : null);
      setNetDebt(nd.status === "fulfilled" ? nd.value : null);
      setRedflags(rf.status === "fulfilled" ? rf.value : null);
      setLoading(false);
    });
  }, [dealId]);

  if (loading) return (
    <div className="grid gap-4 sm:grid-cols-3 lg:grid-cols-6">
      {[1, 2, 3, 4, 5, 6].map((i) => <Skeleton key={i} className="h-24 w-full rounded-lg" />)}
    </div>
  );

  if (!financials) return null;

  const periods = financials.periods;
  const ltmPeriods = periods.slice(-12);
  const ltmRevenue = ltmPeriods.reduce((s, p) => s + Number(financials.revenue[p] ?? 0), 0);
  const latestPeriod = periods[periods.length - 1];
  const latestMargin = financials.ebitda_margin_pct[latestPeriod] ?? 0;
  const recommendedPeg = nwc?.pegs.find((p) => p.recommended) ?? nwc?.pegs[0];

  const tiles = [
    { icon: BarChart2, color: "text-primary", label: "LTM Revenue", value: fmt(ltmRevenue), sub: `${ltmPeriods[0]} – ${ltmPeriods[ltmPeriods.length - 1]}` },
    { icon: TrendingUp, color: "text-green-500", label: "LTM Adjusted EBITDA", value: qoe ? fmt(qoe.ltm_adjusted) : fmt(financials.ebitda[latestPeriod]), sub: qoe ? `${qoe.adjustment_count} QoE adjustments` : "Reported (pre-QoE)" },
    { icon: Percent, color: "text-indigo-500", label: `EBITDA Margin (${latestPeriod})`, value: `${latestMargin.toFixed(1)}%`, sub: "Reported, pre-QoE" },
    { icon: Scale, color: "text-cyan-500", label: "Recommended NWC Peg", value: recommendedPeg ? fmt(recommendedPeg.peg_amount) : "—", sub: recommendedPeg ? recommendedPeg.method.replace(/_/g, " ") : nwc?.message ?? "Unavailable" },
    { icon: Landmark, color: "text-orange-500", label: "Net Debt", value: netDebt?.net_debt ? fmt(netDebt.net_debt) : "—", sub: netDebt?.net_debt_to_ebitda ? `${netDebt.net_debt_to_ebitda.toFixed(2)}x LTM EBITDA` : netDebt?.message ?? "Unavailable" },
    { icon: ShieldAlert, color: "text-rose-500", label: "Red Flags", value: redflags ? `${redflags.summary.high}H / ${redflags.summary.medium}M` : "—", sub: redflags ? `${redflags.summary.total} total` : "Unavailable" },
  ];

  return (
    <div className="grid gap-4 sm:grid-cols-3 lg:grid-cols-6">
      {tiles.map((tile) => (
        <div key={tile.label} className="flex items-start gap-3 rounded-lg border bg-card p-4">
          <tile.icon className={`mt-0.5 h-5 w-5 shrink-0 ${tile.color}`} />
          <div className="min-w-0">
            <p className="text-xs text-muted-foreground uppercase tracking-wide">{tile.label}</p>
            <p className="mt-0.5 text-xl font-bold truncate">{tile.value}</p>
            <p className="text-xs text-muted-foreground truncate">{tile.sub}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
