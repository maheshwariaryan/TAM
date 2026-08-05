export function formatDateTime(value: string) {
  return new Date(value).toLocaleString();
}

export function formatPct(value: number) {
  return `${value.toFixed(2)}%`;
}

export function formatCurrency(value: number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(value);
}

/**
 * Some FDD backend endpoints (financials/pnl, financials/cash-flow) return a
 * `periods` array in YYYY-MM-DD form but key their per-period value records
 * in YYYY-MM form. Try the exact period first (works once/if that's fixed
 * server-side), then fall back to the YYYY-MM prefix.
 */
export function lookupByPeriod<T>(record: Record<string, T>, period: string): T | undefined {
  return record[period] ?? record[period.slice(0, 7)];
}
