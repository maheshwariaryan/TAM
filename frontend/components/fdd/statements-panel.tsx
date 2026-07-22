"use client";

import { useEffect, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { DataTable } from "@/components/tables/data-table";
import { getPnL, getBalanceSheet, type PnLStatement, type BalanceSheet } from "@/lib/api/fdd-client";

const fmt = (v: string | number) =>
  `$${(Math.abs(Number(v)) / 1_000_000).toFixed(1)}M`;

export function StatementsPanel({ dealId }: { dealId: string }) {
  const [pnl, setPnl] = useState<PnLStatement | null>(null);
  const [bs, setBs] = useState<BalanceSheet | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.allSettled([getPnL(dealId, "annual"), getBalanceSheet(dealId)]).then(([p, b]) => {
      setPnl(p.status === "fulfilled" ? p.value : null);
      setBs(b.status === "fulfilled" ? b.value : null);
      setLoading(false);
    });
  }, [dealId]);

  if (loading) return <Skeleton className="h-96 w-full" />;

  if (!pnl) {
    return (
      <Card className="border-dashed">
        <CardContent className="py-8 text-center text-sm text-muted-foreground">
          P&amp;L unavailable — run financial_builder for this deal first.
        </CardContent>
      </Card>
    );
  }

  const periods = pnl.periods.map((p) => p.slice(0, 4));
  const latestYear = periods[periods.length - 1];
  const ltmRevenue = Object.values(pnl.revenue).reduce((s, v) => s + Number(v), 0);
  const ltmEbitda = Object.values(pnl.ebitda).reduce((s, v) => s + Number(v), 0);

  const incomeRows = [
    { id: "is1", line: "Net Revenue", latest: fmt(pnl.revenue[latestYear] ?? 0), ltm: fmt(ltmRevenue) },
    { id: "is2", line: "Gross Profit", latest: fmt(pnl.gross_profit[latestYear] ?? 0), ltm: fmt(Object.values(pnl.gross_profit).reduce((s, v) => s + Number(v), 0)) },
    { id: "is3", line: "EBITDA", latest: fmt(pnl.ebitda[latestYear] ?? 0), ltm: fmt(ltmEbitda) },
    { id: "is4", line: "Net Income", latest: fmt(pnl.net_income[latestYear] ?? 0), ltm: fmt(Object.values(pnl.net_income).reduce((s, v) => s + Number(v), 0)) },
  ];

  const bsLatestPeriod = bs?.periods[bs.periods.length - 1];
  const bsRows = bs
    ? ["Accounts Receivable", "Inventory", "Accounts Payable", "Accrued Liabilities"].map((label, i) => {
        const row = bs.rows.find((r) => r.period === bsLatestPeriod && r.label.toLowerCase().includes(label.split(" ")[0].toLowerCase()));
        return { id: `bs${i}`, line: label, latest: row ? fmt(row.amount) : "—" };
      })
    : [];

  return (
    <div className="space-y-4">
      <DataTable
        title="Standardized Income Statement (Latest Year + Full History)"
        rows={incomeRows}
        columns={[{ key: "line", header: "Line Item" }, { key: "latest", header: `${latestYear}` }, { key: "ltm", header: "Full History" }]}
      />
      {bs ? (
        <DataTable
          title={`Standardized Balance Sheet (${bsLatestPeriod})`}
          rows={bsRows}
          columns={[{ key: "line", header: "Line Item" }, { key: "latest", header: "Amount" }]}
        />
      ) : (
        <Card className="border-dashed"><CardContent className="py-6 text-center text-sm text-muted-foreground">Balance sheet unavailable for this deal.</CardContent></Card>
      )}
    </div>
  );
}
