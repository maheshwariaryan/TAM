import { analysisData, customerData, documentsData, inquiryData, riskData, summaryData } from "@/lib/mock-data/data";
import type { DecisionQueueResponse, Metric } from "@/lib/schemas/types";

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

type FetchOptions = {
  withDelay?: boolean;
};

type CompanyProfile = {
  key: string;
  displayName: string;
  sector: string;
  subSector: string;
  baseRevenueLtm: number;
  monthlyGrowth: number;
  seasonalityAmp: number;
  volatilityAmp: number;
  reportedMargin: number;
  adjustmentPctBase: number;
  nwcPct: number;
  cashConvBase: number;
  riskTilt: number;
  top10Concentration: number;
  top1Ratio: number;
  recurringRevenuePct: number;
  missingCoverageBias: number;
  parsingQuality: number;
  discountRisk: number;
};

function hash(input: string) {
  return Array.from(input).reduce((acc, ch, idx) => acc + ch.charCodeAt(0) * (idx + 1), 0);
}

function rand(seed: number, offset: number) {
  const x = Math.sin(seed * 12.9898 + offset * 78.233) * 43758.5453;
  return x - Math.floor(x);
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function normalizeDealName(deal: string | null) {
  return (deal ?? "Project Atlas").trim();
}

function profileFromSeed(deal: string | null): CompanyProfile {
  const name = normalizeDealName(deal);
  const seed = hash(name.toLowerCase());
  const r1 = rand(seed, 1);
  const r2 = rand(seed, 2);
  const r3 = rand(seed, 3);
  const r4 = rand(seed, 4);

  return {
    key: "seeded",
    displayName: name,
    sector: "Technology",
    subSector: "Vertical SaaS",
    baseRevenueLtm: 38 + r1 * 62,
    monthlyGrowth: -0.003 + r2 * 0.013,
    seasonalityAmp: 0.02 + r3 * 0.05,
    volatilityAmp: 0.02 + r4 * 0.04,
    reportedMargin: 0.13 + r2 * 0.14,
    adjustmentPctBase: 0.03 + r3 * 0.12,
    nwcPct: 0.08 + r4 * 0.08,
    cashConvBase: 30 + r1 * 40,
    riskTilt: 0.15 + r3 * 0.8,
    top10Concentration: 26 + r2 * 27,
    top1Ratio: 0.24 + r4 * 0.12,
    recurringRevenuePct: 56 + r1 * 28,
    missingCoverageBias: 0.2 + r3 * 0.5,
    parsingQuality: 0.82 + r4 * 0.14,
    discountRisk: 0.25 + r2 * 0.7,
  };
}

function getCompanyProfile(deal: string | null): CompanyProfile {
  const normalized = normalizeDealName(deal).toLowerCase();

  if (normalized.includes("apple")) {
    return {
      key: "apple",
      displayName: normalizeDealName(deal),
      sector: "Technology",
      subSector: "Consumer Electronics",
      baseRevenueLtm: 91.4,
      monthlyGrowth: 0.0055,
      seasonalityAmp: 0.024,
      volatilityAmp: 0.018,
      reportedMargin: 0.272,
      adjustmentPctBase: 0.048,
      nwcPct: 0.084,
      cashConvBase: 74,
      riskTilt: 0.22,
      top10Concentration: 24,
      top1Ratio: 0.28,
      recurringRevenuePct: 84,
      missingCoverageBias: 0.14,
      parsingQuality: 0.97,
      discountRisk: 0.31,
    };
  }

  if (normalized.includes("tesla")) {
    return {
      key: "tesla",
      displayName: normalizeDealName(deal),
      sector: "Automotive",
      subSector: "Electric Vehicles",
      baseRevenueLtm: 58.6,
      monthlyGrowth: 0.0038,
      seasonalityAmp: 0.043,
      volatilityAmp: 0.041,
      reportedMargin: 0.178,
      adjustmentPctBase: 0.098,
      nwcPct: 0.148,
      cashConvBase: 46,
      riskTilt: 0.66,
      top10Concentration: 49,
      top1Ratio: 0.33,
      recurringRevenuePct: 61,
      missingCoverageBias: 0.42,
      parsingQuality: 0.89,
      discountRisk: 0.77,
    };
  }

  if (normalized.includes("microsoft")) {
    return {
      key: "microsoft",
      displayName: normalizeDealName(deal),
      sector: "Technology",
      subSector: "Enterprise Software",
      baseRevenueLtm: 76.8,
      monthlyGrowth: 0.0048,
      seasonalityAmp: 0.021,
      volatilityAmp: 0.02,
      reportedMargin: 0.258,
      adjustmentPctBase: 0.042,
      nwcPct: 0.092,
      cashConvBase: 71,
      riskTilt: 0.26,
      top10Concentration: 27,
      top1Ratio: 0.25,
      recurringRevenuePct: 83,
      missingCoverageBias: 0.18,
      parsingQuality: 0.96,
      discountRisk: 0.28,
    };
  }

  if (normalized.includes("meridian")) {
    return {
      key: "meridian",
      displayName: normalizeDealName(deal),
      sector: "Healthcare",
      subSector: "Provider Services",
      baseRevenueLtm: 47.2,
      monthlyGrowth: 0.0023,
      seasonalityAmp: 0.034,
      volatilityAmp: 0.033,
      reportedMargin: 0.186,
      adjustmentPctBase: 0.086,
      nwcPct: 0.142,
      cashConvBase: 43,
      riskTilt: 0.62,
      top10Concentration: 45,
      top1Ratio: 0.31,
      recurringRevenuePct: 64,
      missingCoverageBias: 0.45,
      parsingQuality: 0.86,
      discountRisk: 0.69,
    };
  }

  if (normalized.includes("zenith")) {
    return {
      key: "zenith",
      displayName: normalizeDealName(deal),
      sector: "Industrial",
      subSector: "Specialty Manufacturing",
      baseRevenueLtm: 69.1,
      monthlyGrowth: 0.0042,
      seasonalityAmp: 0.029,
      volatilityAmp: 0.024,
      reportedMargin: 0.224,
      adjustmentPctBase: 0.058,
      nwcPct: 0.104,
      cashConvBase: 63,
      riskTilt: 0.34,
      top10Concentration: 31,
      top1Ratio: 0.27,
      recurringRevenuePct: 78,
      missingCoverageBias: 0.22,
      parsingQuality: 0.93,
      discountRisk: 0.36,
    };
  }

  if (normalized.includes("atlas") || normalized.includes("project atlas")) {
    return {
      key: "atlas",
      displayName: normalizeDealName(deal),
      sector: "Technology",
      subSector: "Vertical SaaS",
      baseRevenueLtm: 63.7,
      monthlyGrowth: 0.0031,
      seasonalityAmp: 0.03,
      volatilityAmp: 0.026,
      reportedMargin: 0.192,
      adjustmentPctBase: 0.092,
      nwcPct: 0.118,
      cashConvBase: 52,
      riskTilt: 0.49,
      top10Concentration: 41,
      top1Ratio: 0.29,
      recurringRevenuePct: 69,
      missingCoverageBias: 0.31,
      parsingQuality: 0.9,
      discountRisk: 0.57,
    };
  }

  return profileFromSeed(deal);
}

function periodFactor(period: string | null) {
  return period === "Annual" ? 1.08 : period === "Quarterly" ? 1.03 : 1;
}

function basisFactor(basis: string | null) {
  return basis === "Pro Forma" ? 1.06 : basis === "Reported" ? 1 : 1.01;
}

function modelMultiplier(period: string | null, basis: string | null) {
  return periodFactor(period) * basisFactor(basis);
}

function clone<T>(v: T): T {
  return JSON.parse(JSON.stringify(v));
}

function moneyM(value: number) {
  return `$${value.toFixed(1)}M`;
}

function pct(value: number) {
  return `${value.toFixed(1)}%`;
}

function rollupTrend(deal: string | null, period: string | null, basis: string | null) {
  const profile = getCompanyProfile(deal);
  const seed = hash(profile.displayName.toLowerCase());
  const mult = modelMultiplier(period, basis);
  const months = summaryData.trend.map((row) => row.month);
  const baseMonthlyRevenue = (profile.baseRevenueLtm / 12) * mult;

  return months.map((month, idx) => {
    const phase = (idx / 12) * Math.PI * 2 + (seed % 9) * 0.15;
    const seasonality = 1 + Math.sin(phase) * profile.seasonalityAmp;
    const growth = 1 + profile.monthlyGrowth * idx;
    const volatility = 1 + (rand(seed, idx + 11) - 0.5) * profile.volatilityAmp;
    const revenue = baseMonthlyRevenue * seasonality * growth * volatility;
    const reportedMargin = clamp(profile.reportedMargin + Math.cos(phase * 1.1) * 0.008, 0.09, 0.36);
    const reportedEbitda = revenue * reportedMargin;
    const adjustmentPct = clamp(profile.adjustmentPctBase + (rand(seed, idx + 101) - 0.5) * 0.02, 0.01, 0.23);
    const adjustedEbitda = reportedEbitda * (1 + adjustmentPct);
    const nwc = revenue * profile.nwcPct * (0.94 + rand(seed, idx + 201) * 0.12);
    const cashConversion = clamp(
      profile.cashConvBase + Math.sin(phase * 0.8) * 6 - profile.adjustmentPctBase * 120 + (rand(seed, idx + 301) - 0.5) * 4,
      -10,
      88
    );
    const ocf = adjustedEbitda * (cashConversion / 100);

    return {
      month,
      revenue: Number(revenue.toFixed(2)),
      reportedEbitda: Number(reportedEbitda.toFixed(2)),
      adjustedEbitda: Number(adjustedEbitda.toFixed(2)),
      nwc: Number(nwc.toFixed(2)),
      cashConversion: Number(cashConversion.toFixed(1)),
      ocf: Number(ocf.toFixed(2)),
    };
  });
}

function summarizeNumbers(trend: ReturnType<typeof rollupTrend>) {
  const revenueLtm = trend.reduce((sum, t) => sum + t.revenue, 0);
  const reportedEbitdaLtm = trend.reduce((sum, t) => sum + t.reportedEbitda, 0);
  const adjustedEbitdaLtm = trend.reduce((sum, t) => sum + t.adjustedEbitda, 0);
  const avgNwc = trend.reduce((sum, t) => sum + t.nwc, 0) / trend.length;
  const avgCashConversion = trend.reduce((sum, t) => sum + t.cashConversion, 0) / trend.length;
  const adjustments = adjustedEbitdaLtm - reportedEbitdaLtm;
  const adjustmentPct = (adjustments / Math.max(reportedEbitdaLtm, 0.1)) * 100;

  return {
    revenueLtm,
    reportedEbitdaLtm,
    adjustedEbitdaLtm,
    avgNwc,
    avgCashConversion,
    adjustments,
    adjustmentPct,
  };
}

type Benchmark = NonNullable<Metric["benchmark"]>;

function benchmarkForMetric(
  profile: CompanyProfile,
  metricId: string,
  companyValue: number,
  unit: Benchmark["unit"],
  direction: Benchmark["direction"],
  volatility: number
): Benchmark {
  const spread = Math.max(companyValue * volatility, unit === "count" ? 1 : 0.8);
  const sectorMedian = clamp(companyValue * (1 + (profile.riskTilt - 0.4) * 0.12), companyValue - spread * 0.9, companyValue + spread * 0.9);
  const subSectorMedian = clamp(sectorMedian * (1 + (profile.discountRisk - 0.45) * 0.08), sectorMedian - spread * 0.7, sectorMedian + spread * 0.7);
  const lowerQuartile = Math.max(0, Math.min(sectorMedian, subSectorMedian) - spread);
  const upperQuartile = Math.max(lowerQuartile + 0.01, Math.max(sectorMedian, subSectorMedian) + spread);

  return {
    sector: profile.sector,
    subSector: profile.subSector,
    lowerQuartile: Number(lowerQuartile.toFixed(metricId === "overall-risk" ? 1 : 2)),
    upperQuartile: Number(upperQuartile.toFixed(metricId === "overall-risk" ? 1 : 2)),
    sectorMedian: Number(sectorMedian.toFixed(metricId === "overall-risk" ? 1 : 2)),
    subSectorMedian: Number(subSectorMedian.toFixed(metricId === "overall-risk" ? 1 : 2)),
    companyValue: Number(companyValue.toFixed(metricId === "overall-risk" ? 1 : 2)),
    unit,
    direction,
  };
}

function summaryBenchmarks(
  profile: CompanyProfile,
  numbers: ReturnType<typeof summarizeNumbers>,
  riskScore: number
): Partial<Record<string, Benchmark>> {
  return {
    "revenue-ltm": benchmarkForMetric(profile, "revenue-ltm", numbers.revenueLtm, "currency_m", "higher_better", 0.14),
    "reported-ebitda": benchmarkForMetric(profile, "reported-ebitda", numbers.reportedEbitdaLtm, "currency_m", "higher_better", 0.18),
    "adjusted-ebitda": benchmarkForMetric(profile, "adjusted-ebitda", numbers.adjustedEbitdaLtm, "currency_m", "higher_better", 0.18),
    "adj-pct": benchmarkForMetric(profile, "adj-pct", numbers.adjustmentPct, "percent", "lower_better", 0.2),
    "avg-nwc": benchmarkForMetric(profile, "avg-nwc", numbers.avgNwc, "currency_m", "target_band", 0.16),
    "nwc-peg": benchmarkForMetric(profile, "nwc-peg", numbers.avgNwc * 1.03, "currency_m", "target_band", 0.15),
    "cash-conv": benchmarkForMetric(profile, "cash-conv", numbers.avgCashConversion, "percent", "higher_better", 0.2),
    "overall-risk": benchmarkForMetric(profile, "overall-risk", riskScore, "ratio", "lower_better", 0.22),
  };
}

function dashboardBenchmarkCatalog(
  profile: CompanyProfile,
  trend: ReturnType<typeof rollupTrend>,
  numbers: ReturnType<typeof summarizeNumbers>,
  riskScore: number
): Partial<Record<string, Benchmark>> {
  const revenueAvg = numbers.revenueLtm / Math.max(trend.length, 1);
  const revenueGrowthYoY = ((trend[trend.length - 1]?.revenue ?? 0) / Math.max(trend[0]?.revenue ?? 1, 0.1) - 1) * 100;
  const revenueGrowthQoQ = ((trend[trend.length - 1]?.revenue ?? 0) / Math.max(trend[trend.length - 4]?.revenue ?? 1, 0.1) - 1) * 100;
  const adjustedLtm = numbers.adjustedEbitdaLtm;
  const adjPct = numbers.adjustmentPct;

  const base = summaryBenchmarks(profile, numbers, riskScore);

  return {
    ...base,
    "rev-growth": benchmarkForMetric(profile, "rev-growth", revenueGrowthYoY, "percent", "higher_better", 0.28),
    "ebitda-margin-vs": benchmarkForMetric(profile, "ebitda-margin-vs", ((adjustedLtm / Math.max(revenueAvg * 12, 0.1)) * 100), "percent", "higher_better", 0.2),
    "normalized-earnings": benchmarkForMetric(profile, "normalized-earnings", adjustedLtm * 0.98, "currency_m", "higher_better", 0.2),
    "run-rate-earnings": benchmarkForMetric(profile, "run-rate-earnings", adjustedLtm * 1.01, "currency_m", "higher_better", 0.2),
    "nwc-rev-pct": benchmarkForMetric(profile, "nwc-rev-pct", ((numbers.avgNwc / Math.max(revenueAvg, 0.1)) * 100), "percent", "target_band", 0.14),
    "highrisk-ebitda-impact": benchmarkForMetric(profile, "highrisk-ebitda-impact", Math.max(2.1, adjPct * 0.58), "percent", "lower_better", 0.24),
    "delta-adj-ebitda": benchmarkForMetric(profile, "delta-adj-ebitda", Math.max(0.12, adjustedLtm * 0.018), "currency_m", "higher_better", 0.35),
    "new-adjustments": benchmarkForMetric(profile, "new-adjustments", Math.max(0.2, adjustedLtm * 0.034), "currency_m", "lower_better", 0.26),
    "new-risks": benchmarkForMetric(profile, "new-risks", Math.max(1, Math.round(Math.abs(revenueGrowthQoQ) / 2.4)), "count", "lower_better", 0.42),
    "risk-split": benchmarkForMetric(profile, "risk-split", Math.max(18, Math.min(44, 16 + Math.abs(revenueGrowthQoQ))), "percent", "lower_better", 0.24),
    "tax-deferred": benchmarkForMetric(profile, "tax-deferred", 1.1, "currency_m", "target_band", 0.18),
    "tax-nol": benchmarkForMetric(profile, "tax-nol", 2.6, "currency_m", "target_band", 0.22),
    "tax-vat": benchmarkForMetric(profile, "tax-vat", 0.4, "currency_m", "lower_better", 0.25),
    "tax-payroll": benchmarkForMetric(profile, "tax-payroll", 0.2, "currency_m", "lower_better", 0.28),
    "tax-jurisdiction": benchmarkForMetric(profile, "tax-jurisdiction", 5, "count", "lower_better", 0.2),
  };
}

function calculateRiskScore(
  profile: CompanyProfile,
  numbers: ReturnType<typeof summarizeNumbers>,
  period: string | null,
  basis: string | null
) {
  const mode = modelMultiplier(period, basis);
  const score =
    3.2 +
    profile.riskTilt * 2.3 +
    numbers.adjustmentPct * 0.08 +
    (numbers.avgCashConversion < 60 ? 0.85 : 0) +
    (numbers.avgNwc / Math.max(numbers.revenueLtm, 1)) * 11 +
    (mode > 1.03 ? 0.25 : 0);

  return clamp(score, 1.4, 9.6);
}

function tieOutStatus(variancePct: number, tolerancePct: number): "Pass" | "Warn" | "Fail" {
  if (variancePct <= tolerancePct) return "Pass";
  if (variancePct <= tolerancePct * 1.5) return "Warn";
  return "Fail";
}

function withOptionalDelay(options?: FetchOptions) {
  return options?.withDelay === false ? Promise.resolve() : delay(300 + Math.round(Math.random() * 300));
}

export async function getSummary(
  period: string | null,
  basis: string | null,
  deal: string | null,
  options?: FetchOptions
) {
  await withOptionalDelay(options);
  const profile = getCompanyProfile(deal);
  const trend = rollupTrend(deal, period, basis);
  const numbers = summarizeNumbers(trend);
  const riskScore = calculateRiskScore(profile, numbers, period, basis);
  const benchmarkCatalog = dashboardBenchmarkCatalog(profile, trend, numbers, riskScore);
  const data = clone(summaryData);

  data.lastUpdated = new Date().toISOString();
  data.trend = trend;
  data.metrics = data.metrics
    .map((metric): Metric => {
    if (metric.id === "revenue-ltm") {
      return { ...metric, value: moneyM(numbers.revenueLtm), delta: pct((trend[11].revenue / Math.max(trend[8].revenue, 0.1) - 1) * 100) };
    }
    if (metric.id === "reported-ebitda") {
      return { ...metric, value: moneyM(numbers.reportedEbitdaLtm) };
    }
    if (metric.id === "adjusted-ebitda") {
      return { ...metric, value: moneyM(numbers.adjustedEbitdaLtm) };
    }
    if (metric.id === "adj-pct") {
      return {
        ...metric,
        value: pct(numbers.adjustmentPct),
        severity: numbers.adjustmentPct > 10 ? "Red" : numbers.adjustmentPct > 7 ? "Amber" : "Green",
      };
    }
    if (metric.id === "avg-nwc") {
      return { ...metric, value: moneyM(numbers.avgNwc) };
    }
    if (metric.id === "nwc-peg") {
      return { ...metric, value: moneyM(numbers.avgNwc * 1.03) };
    }
    if (metric.id === "cash-conv") {
      return {
        ...metric,
        value: `${numbers.avgCashConversion.toFixed(0)}%`,
        severity: numbers.avgCashConversion < 30 ? "Red" : numbers.avgCashConversion < 60 ? "Amber" : "Green",
      };
    }
    if (metric.id === "overall-risk") {
      return {
        ...metric,
        value: `${riskScore.toFixed(1)} / 10`,
        severity: riskScore >= 7 ? "Red" : riskScore >= 4.5 ? "Amber" : "Green",
      };
    }
    return metric;
  })
    .map((metric) => ({ ...metric, benchmark: benchmarkCatalog[metric.id] }));
  data.benchmarkCatalog = Object.entries(benchmarkCatalog).reduce<Array<{ metricId: string; benchmark: Benchmark }>>((acc, [metricId, benchmark]) => {
    if (benchmark) acc.push({ metricId, benchmark });
    return acc;
  }, []);

  const failCount = riskScore >= 7 ? 3 : riskScore >= 5 ? 2 : 1;
  data.riskBreakdown = { red: failCount, amber: Math.max(2, 7 - failCount) };
  data.insights = data.insights.map((insight, idx) => ({
    ...insight,
    body:
      idx === 0
        ? `Adjusted EBITDA is ${moneyM(numbers.adjustedEbitdaLtm)} with ${pct(numbers.adjustmentPct)} adjustment intensity for ${profile.displayName}.`
        : idx === 1
          ? `Average NWC is ${moneyM(numbers.avgNwc)} and cash conversion is ${numbers.avgCashConversion.toFixed(0)}%, indicating ${numbers.avgCashConversion < 55 ? "moderate drag" : "healthy realization"}.`
          : `Revenue run-rate is ${moneyM(numbers.revenueLtm)}. Last-quarter movement is ${pct((trend[11].revenue / Math.max(trend[8].revenue, 0.1) - 1) * 100)}.`,
  }));
  data.deltaFeed = [
    {
      id: "d1",
      type: "New File",
      message: `${profile.displayName} source package refreshed (${period ?? "Monthly"}, ${basis ?? "Reported"}).`,
      timestamp: new Date(Date.now() - 1000 * 60 * 14).toISOString(),
    },
    {
      id: "d2",
      type: "Adjustment",
      message: `Adjustment intensity recalculated at ${pct(numbers.adjustmentPct)}.`,
      timestamp: new Date(Date.now() - 1000 * 60 * 28).toISOString(),
    },
    {
      id: "d3",
      type: "Tie-out",
      message: `Risk score now ${riskScore.toFixed(1)}/10 with ${data.riskBreakdown.red} red concentrations.`,
      timestamp: new Date(Date.now() - 1000 * 60 * 46).toISOString(),
    },
    {
      id: "d4",
      type: "Anomaly",
      message: `Cash conversion trend is ${numbers.avgCashConversion < 60 ? "below target" : "within target"} for ${profile.displayName}.`,
      timestamp: new Date(Date.now() - 1000 * 60 * 61).toISOString(),
    },
  ];

  return data;
}

export async function getAnalysis(
  period: string | null,
  basis: string | null,
  deal: string | null,
  options?: FetchOptions
) {
  await withOptionalDelay(options);
  const profile = getCompanyProfile(deal);
  const data = clone(analysisData);
  const trend = rollupTrend(deal, period, basis);
  const numbers = summarizeNumbers(trend);
  const mult = modelMultiplier(period, basis);

  data.lastUpdated = new Date().toISOString();
  data.trend = trend;

  const recurringRevenuePct = clamp(profile.recurringRevenuePct - profile.riskTilt * 6 + (mult - 1) * 6, 45, 92);
  const top10 = clamp(profile.top10Concentration + profile.riskTilt * 3 + (mult - 1) * 8, 20, 70);

  data.revenueMetrics = data.revenueMetrics.map((metric): Metric => {
    if (metric.id === "rev-reported-norm") {
      return { ...metric, value: `${moneyM(numbers.revenueLtm)} / ${moneyM(numbers.revenueLtm * 0.986)}` };
    }
    if (metric.id === "rev-growth") {
      return { ...metric, value: pct((trend[11].revenue / Math.max(trend[0].revenue, 0.1) - 1) * 100) };
    }
    if (metric.id === "rev-recurring") {
      return { ...metric, value: pct(recurringRevenuePct) };
    }
    if (metric.id === "rev-top1") {
      const top1 = clamp(top10 * profile.top1Ratio, 6, 25);
      const top3 = clamp(top10 * 0.6, 14, 50);
      const top5 = clamp(top10 * 0.8, 20, 65);
      return { ...metric, value: `${top1.toFixed(0)}% / ${top3.toFixed(0)}% / ${top5.toFixed(0)}% / ${top10.toFixed(0)}%` };
    }
    if (metric.id === "rev-vol") {
      return { ...metric, value: pct(clamp(4.2 + profile.volatilityAmp * 120, 2.8, 16.5)) };
    }
    if (metric.id === "rev-eom") {
      const flags = Math.max(0, Math.round(profile.discountRisk * 4 - 0.8));
      return { ...metric, value: String(flags), severity: flags >= 3 ? "Red" : flags >= 1 ? "Amber" : "Green" };
    }
    return metric;
  });

  data.qoeMetrics = data.qoeMetrics.map((metric): Metric => {
    if (metric.id === "qoe-reported-ebitda") return { ...metric, value: moneyM(numbers.reportedEbitdaLtm) };
    if (metric.id === "qoe-adjusted-ebitda") return { ...metric, value: moneyM(numbers.adjustedEbitdaLtm) };
    if (metric.id === "qoe-adjustment-pct") return { ...metric, value: pct(numbers.adjustmentPct) };
    if (metric.id === "qoe-rec-vs-non") {
      const recurring = clamp(84 - numbers.adjustmentPct, 58, 92);
      return { ...metric, value: `${recurring.toFixed(0)}% / ${(100 - recurring).toFixed(0)}%` };
    }
    if (metric.id === "qoe-highrisk") {
      const highRisk = Math.max(1, Math.round(numbers.adjustmentPct / 2.6));
      return { ...metric, value: String(highRisk), severity: highRisk >= 4 ? "Red" : highRisk >= 2 ? "Amber" : "Green" };
    }
    if (metric.id === "qoe-margin") {
      return { ...metric, value: pct((numbers.adjustedEbitdaLtm / Math.max(numbers.revenueLtm, 0.1)) * 100) };
    }
    if (metric.id === "qoe-count") {
      return { ...metric, value: String(Math.max(8, Math.round(numbers.adjustmentPct * 1.5))) };
    }
    return metric;
  });

  data.marginMetrics = data.marginMetrics.map((metric): Metric => {
    if (metric.id === "margin-gross") {
      return { ...metric, value: pct(clamp((1 - (0.56 - profile.reportedMargin * 0.42)) * 100, 28, 72)) };
    }
    if (metric.id === "margin-ebitda") return { ...metric, value: pct((numbers.reportedEbitdaLtm / Math.max(numbers.revenueLtm, 0.1)) * 100) };
    if (metric.id === "margin-opex") return { ...metric, value: pct(clamp(21 + profile.riskTilt * 8 + numbers.adjustmentPct * 0.12, 16, 40)) };
    if (metric.id === "margin-cogs") {
      const gross = clamp((1 - (0.56 - profile.reportedMargin * 0.42)) * 100, 28, 72);
      return { ...metric, value: pct(100 - gross) };
    }
    if (metric.id === "margin-onetime") return { ...metric, value: moneyM(Math.max(0.2, numbers.adjustments * 0.36)) };
    if (metric.id === "margin-spikes") {
      const spikes = Math.max(0, Math.round(profile.riskTilt * 5 - 1));
      return { ...metric, value: String(spikes), severity: spikes >= 3 ? "Red" : spikes >= 1 ? "Amber" : "Green" };
    }
    if (metric.id === "margin-payroll") return { ...metric, value: pct(clamp(30 + profile.riskTilt * 14, 20, 54)) };
    return metric;
  });

  const avgNwc = numbers.avgNwc;
  data.wcMetrics = data.wcMetrics.map((metric): Metric => {
    if (metric.id === "wc-avg") return { ...metric, value: moneyM(avgNwc) };
    if (metric.id === "wc-peg") return { ...metric, value: moneyM(avgNwc * 1.03) };
    if (metric.id === "wc-dso") {
      const dso = clamp((avgNwc / Math.max(numbers.revenueLtm / 12, 0.1)) * 29, 24, 63);
      const dpo = clamp(dso * (0.66 + profile.riskTilt * 0.18), 16, 49);
      const dio = clamp(dso * (1.05 + profile.riskTilt * 0.26), 18, 72);
      const ccc = dso + dio - dpo;
      return { ...metric, value: `${dso.toFixed(0)} / ${dpo.toFixed(0)} / ${dio.toFixed(0)} / ${ccc.toFixed(0)}` };
    }
    if (metric.id === "wc-ar60") {
      const ar60 = clamp(4.4 + profile.riskTilt * 11, 2, 22);
      return { ...metric, value: pct(ar60), severity: ar60 > 12 ? "Red" : ar60 > 8 ? "Amber" : "Green" };
    }
    if (metric.id === "wc-ap60") {
      const ap60 = clamp(3.6 + profile.riskTilt * 8, 2, 20);
      return { ...metric, value: pct(ap60), severity: ap60 > 10 ? "Amber" : "Green" };
    }
    return metric;
  });

  data.cashMetrics = data.cashMetrics.map((metric): Metric => {
    if (metric.id === "cash-ocf") return { ...metric, value: moneyM(trend.reduce((sum, t) => sum + t.ocf, 0)) };
    if (metric.id === "cash-conv") return { ...metric, value: `${numbers.avgCashConversion.toFixed(0)}%` };
    if (metric.id === "cash-capex") return { ...metric, value: moneyM(Math.max(0.8, numbers.revenueLtm * (0.028 + profile.riskTilt * 0.01))) };
    if (metric.id === "cash-fcf") {
      const ocf = trend.reduce((sum, t) => sum + t.ocf, 0);
      const capex = Math.max(0.8, numbers.revenueLtm * (0.028 + profile.riskTilt * 0.01));
      return { ...metric, value: moneyM(ocf - capex) };
    }
    if (metric.id === "cash-runway") {
      const runway = clamp(24 - profile.riskTilt * 14 + numbers.avgCashConversion / 10, 3, 30);
      return { ...metric, value: `${Math.round(runway)} months` };
    }
    if (metric.id === "cash-wcdrag") return { ...metric, value: moneyM(Math.max(0.2, numbers.avgNwc * (0.08 + profile.riskTilt * 0.06))) };
    if (metric.id === "cash-neg") {
      const neg = trend.filter((row) => row.ocf < 0).length;
      return { ...metric, value: String(neg), severity: neg >= 3 ? "Red" : neg >= 1 ? "Amber" : "Green" };
    }
    return metric;
  });

  const top1 = clamp(top10 * profile.top1Ratio, 6, 25);
  data.concentration = [
    { label: "Top 1", value: Number(top1.toFixed(1)) },
    { label: "Top 3", value: Number((top10 * 0.6).toFixed(1)) },
    { label: "Top 5", value: Number((top10 * 0.8).toFixed(1)) },
    { label: "Top 10", value: Number(top10.toFixed(1)) },
  ];

  data.aging = [
    { bucket: "0-30", ar: Number(clamp(58 - profile.riskTilt * 12, 30, 80).toFixed(1)), ap: Number(clamp(52 - profile.riskTilt * 8, 24, 78).toFixed(1)) },
    { bucket: "31-60", ar: Number(clamp(27 + profile.riskTilt * 7, 12, 40).toFixed(1)), ap: Number(clamp(31 + profile.riskTilt * 8, 14, 45).toFixed(1)) },
    { bucket: "61-90", ar: Number(clamp(10 + profile.riskTilt * 4, 3, 20).toFixed(1)), ap: Number(clamp(11 + profile.riskTilt * 4, 3, 20).toFixed(1)) },
    { bucket: "90+", ar: Number(clamp(5 + profile.riskTilt * 3, 1, 16).toFixed(1)), ap: Number(clamp(6 + profile.riskTilt * 3, 1, 16).toFixed(1)) },
  ];

  data.opexMix = [
    { name: "Payroll", value: Number(clamp(30 + profile.riskTilt * 12, 20, 52).toFixed(1)) },
    { name: "G&A", value: Number(clamp(19 + profile.riskTilt * 4, 12, 28).toFixed(1)) },
    { name: "Sales", value: Number(clamp(18 + (1 - profile.riskTilt) * 3, 12, 28).toFixed(1)) },
    { name: "IT", value: Number(clamp(9 + (1 - profile.riskTilt) * 5, 6, 22).toFixed(1)) },
    {
      name: "Other",
      value: Number(
        clamp(
          100 -
            (30 + profile.riskTilt * 12) -
            (19 + profile.riskTilt * 4) -
            (18 + (1 - profile.riskTilt) * 3) -
            (9 + (1 - profile.riskTilt) * 5),
          4,
          18
        ).toFixed(1)
      ),
    },
  ];

  data.adjustments = data.adjustments.map((row, idx) => {
    const amount = Math.round(numbers.adjustments * 1_000_000 * (0.16 + idx * 0.12) * (0.8 + profile.riskTilt * 0.6));
    const status = idx <= 1 ? "Accepted" : idx === 2 ? "Reviewed" : profile.riskTilt > 0.58 ? "Proposed" : "Reviewed";
    return { ...row, amount, status };
  });

  return data;
}

export async function getRisk(
  deal: string | null,
  period: string | null,
  basis: string | null,
  options?: FetchOptions
) {
  await withOptionalDelay(options);
  const profile = getCompanyProfile(deal);
  const data = clone(riskData);
  const trend = rollupTrend(deal, period, basis);
  const numbers = summarizeNumbers(trend);
  const seed = hash(profile.displayName.toLowerCase());
  const riskScore = calculateRiskScore(profile, numbers, period, basis);

  data.lastUpdated = new Date().toISOString();
  data.riskScore = Number(riskScore.toFixed(1));
  data.dimensions = data.dimensions.map((row, idx) => {
    const drift = ((idx % 3) - 1) * 0.45 + (rand(seed, idx + 40) - 0.5) * 0.8;
    const score = clamp(riskScore + drift + profile.riskTilt * 0.5, 1.5, 9.7);
    return { ...row, score: Number(score.toFixed(1)) };
  });

  const baseRevenue = numbers.revenueLtm;
  const tieOutTemplates = [
    { name: "TB <-> IS (Revenue)", expected: baseRevenue, tolerancePct: 0.25 },
    { name: "TB <-> BS (A=L+E)", expected: baseRevenue * 2.02, tolerancePct: 0.2 },
    { name: "AR Aging <-> BS AR", expected: numbers.avgNwc * 0.98, tolerancePct: 0.5 },
    { name: "AP Aging <-> BS AP", expected: numbers.avgNwc * 0.74, tolerancePct: 1.0 },
    { name: "Cash <-> Bank", expected: numbers.adjustedEbitdaLtm * 0.24, tolerancePct: 0.5 },
    { name: "GL rollforward <-> TB", expected: baseRevenue * 2.02, tolerancePct: 0.4 },
  ];

  data.tieOuts = tieOutTemplates.map((tpl, idx) => {
    const varianceBase =
      tpl.tolerancePct *
      (0.45 + profile.riskTilt * 1.45 + rand(seed, idx + 120) * 1.25) *
      (idx % 2 === 0 ? 0.84 : 1.09);
    const variancePct = Number(Math.max(0.04, varianceBase).toFixed(2));
    const observed = tpl.expected * (1 - variancePct / 100);
    const diff = observed - tpl.expected;
    const status = tieOutStatus(variancePct, tpl.tolerancePct);
    return {
      name: tpl.name,
      expected: Math.round(tpl.expected),
      observed: Math.round(observed),
      diff: Math.round(diff),
      variancePct,
      tolerancePct: tpl.tolerancePct,
      status,
    };
  });

  const failCount = data.tieOuts.filter((t) => t.status === "Fail").length;
  const warnCount = data.tieOuts.filter((t) => t.status === "Warn").length;

  data.register = data.register.map((row, idx) => {
    const severity: "Red" | "Amber" | "Green" = idx < failCount ? "Red" : idx < failCount + warnCount + 1 ? "Amber" : "Green";
    return {
      ...row,
      severity,
      status: severity === "Green" ? "Mitigated" : "Open",
      exposureRange:
        severity === "Red"
          ? "$0.5M-$1.0M"
          : severity === "Amber"
            ? "$0.2M-$0.6M"
            : "<$0.2M",
    };
  });

  return data;
}

export async function getDocuments(deal: string | null, options?: FetchOptions) {
  await withOptionalDelay(options);
  const profile = getCompanyProfile(deal);
  const data = clone(documentsData);
  const seed = hash(profile.displayName.toLowerCase());

  data.lastUpdated = new Date().toISOString();
  data.coverage = data.coverage.map((row, scheduleIdx) => ({
    ...row,
    months: row.months.map((month, monthIdx) => {
      const r = rand(seed, scheduleIdx * 37 + monthIdx * 17);
      const latePeriod = monthIdx >= row.months.length - 4;
      const missingThreshold = profile.missingCoverageBias * (latePeriod ? 0.32 : 0.12);
      const partialThreshold = 0.18 + profile.missingCoverageBias * (latePeriod ? 0.22 : 0.12);
      const status: "Available" | "Partial" | "Missing" =
        r < missingThreshold ? "Missing" : r < partialThreshold ? "Partial" : "Available";
      return { ...month, status };
    }),
  }));
  data.inventory = data.inventory.map((row, idx) => ({
    ...row,
    entity: profile.displayName || row.entity,
    confidence: Number(clamp(profile.parsingQuality - 0.05 + rand(seed, idx + 220) * 0.12, 0.7, 0.99).toFixed(2)),
  }));
  const missingCount = data.coverage.reduce((acc, sched) => acc + sched.months.filter((m) => m.status === "Missing").length, 0);
  data.pbc = data.pbc.map((row, idx) => {
    const severity: "Green" | "Amber" | "Red" =
      idx === 0 && missingCount > 5 ? "Red" : idx === 1 && profile.riskTilt > 0.55 ? "Red" : idx === 2 && missingCount > 2 ? "Amber" : row.severity;
    return { ...row, severity };
  });

  return data;
}

export async function getCustomer(
  period: string | null,
  basis: string | null,
  deal: string | null,
  options?: FetchOptions
) {
  await withOptionalDelay(options);
  const profile = getCompanyProfile(deal);
  const data = clone(customerData);
  const seed = hash(profile.displayName.toLowerCase());
  const mult = modelMultiplier(period, basis);
  const top10Base = clamp(profile.top10Concentration + profile.riskTilt * 3 + (mult - 1) * 8, 20, 70);
  const top1Base = clamp(top10Base * profile.top1Ratio, 6, 25);

  data.lastUpdated = new Date().toISOString();
  data.topTrend = data.topTrend.map((row, idx) => ({
    ...row,
    top1: Number((top1Base + idx * 0.07 * mult + Math.sin((idx + seed % 5) / 3) * 0.08).toFixed(2)),
    top10: Number((top10Base + idx * 0.11 * mult + Math.cos((idx + seed % 7) / 3) * 0.14).toFixed(2)),
  }));
  data.discountAnomalies = data.discountAnomalies.map((row, idx) => {
    const priorRate = 0.024 + idx * (0.001 + profile.discountRisk * 0.0005);
    const spikeMultiplier = idx >= data.discountAnomalies.length - 2 ? 1.2 + profile.discountRisk * 0.9 : 1 + profile.discountRisk * 0.35;
    const rate = priorRate * spikeMultiplier;
    return {
      ...row,
      priorRate: Number(priorRate.toFixed(4)),
      rate: Number(rate.toFixed(4)),
      flagged: rate > priorRate * 1.5,
    };
  });

  data.metrics = data.metrics.map((metric): Metric => {
    if (metric.id === "cust-top10") {
      return { ...metric, value: `${data.topTrend[data.topTrend.length - 1].top10.toFixed(0)}%` };
    }
    if (metric.id === "cust-largest") {
      return { ...metric, value: `${data.topTrend[data.topTrend.length - 1].top1.toFixed(0)}%` };
    }
    if (metric.id === "cust-nrr") {
      const nrr = clamp(95 + profile.recurringRevenuePct * 0.22 - profile.riskTilt * 9, 78, 128);
      return { ...metric, value: `${nrr.toFixed(0)}%` };
    }
    if (metric.id === "cust-disc") {
      const anomalies = data.discountAnomalies.filter((entry) => entry.flagged).length;
      return { ...metric, value: String(anomalies), severity: anomalies >= 3 ? "Red" : anomalies >= 1 ? "Amber" : "Green" };
    }
    return metric;
  });

  return data;
}

export async function getInquiry(
  deal: string | null,
  period: string | null,
  basis: string | null,
  options?: FetchOptions
) {
  await withOptionalDelay(options);
  const profile = getCompanyProfile(deal);
  const risk = await getRisk(deal, period, basis, { withDelay: false });
  const docs = await getDocuments(deal, { withDelay: false });
  const customer = await getCustomer(period, basis, deal, { withDelay: false });
  const base = clone(inquiryData);
  const seed = hash(profile.displayName.toLowerCase());
  const discountFlags = customer.discountAnomalies.filter((entry) => entry.flagged).length;

  const dynamic = base.map((row, idx) => ({
    ...row,
    id: `INQ-${(seed % 9000) + 1000 + idx}`,
    status: idx === 0 && risk.tieOuts.some((t) => t.status === "Fail") ? "Open" : row.status,
    blocking: idx < Math.max(1, Math.floor(risk.tieOuts.filter((t) => t.status !== "Pass").length / 2)),
  }));

  const missingCount = docs.coverage.reduce((acc, sched) => acc + sched.months.filter((m) => m.status === "Missing").length, 0);
  if (missingCount > 0) {
    dynamic.unshift({
      id: `INQ-${(seed % 9000) + 9999}`,
      request: `Provide missing schedules support for ${profile.displayName} (${missingCount} missing coverage cells)`,
      owner: "Data Room Owner",
      dueDate: "2026-03-01",
      status: "Open",
      blocking: true,
    });
  }
  if (discountFlags > 0) {
    dynamic.unshift({
      id: `INQ-${(seed % 9000) + 8888}`,
      request: `Explain ${discountFlags} discount anomaly flag(s) and supporting commercial terms.`,
      owner: "Revenue Ops",
      dueDate: "2026-03-03",
      status: profile.riskTilt > 0.55 ? "Open" : "Monitoring",
      blocking: profile.riskTilt > 0.7,
    });
  }

  return {
    lastUpdated: new Date().toISOString(),
    inquiries: dynamic,
  };
}

export async function getDecisionQueue(
  deal: string | null,
  period: string | null,
  basis: string | null,
  options?: FetchOptions
): Promise<DecisionQueueResponse> {
  await withOptionalDelay(options);
  const [summary, analysis, risk, docs, inquiry] = await Promise.all([
    getSummary(period, basis, deal, { withDelay: false }),
    getAnalysis(period, basis, deal, { withDelay: false }),
    getRisk(deal, period, basis, { withDelay: false }),
    getDocuments(deal, { withDelay: false }),
    getInquiry(deal, period, basis, { withDelay: false }),
  ]);

  const failTieOuts = risk.tieOuts.filter((row) => row.status === "Fail");
  const warnTieOuts = risk.tieOuts.filter((row) => row.status === "Warn");
  const blockingInquiries = inquiry.inquiries.filter((row) => row.blocking && row.status !== "Closed");
  const highRiskAdjustments = analysis.adjustments
    .filter((row) => row.status !== "Accepted")
    .sort((a, b) => b.amount - a.amount)
    .slice(0, 3);
  const missingCoverage = docs.coverage
    .flatMap((schedule) => schedule.months.map((month) => ({ schedule: schedule.schedule, month })))
    .filter((entry) => entry.month.status === "Missing")
    .slice(0, 4);

  const items = [
    ...failTieOuts.map((tie, idx) => ({
      id: `dq-risk-fail-${idx + 1}`,
      title: `Resolve tie-out failure: ${tie.name}`,
      impactArea: "Risk / Tie-out",
      impactScore: Number((95 - idx * 4).toFixed(1)),
      owner: "Finance Controller",
      dueDate: "2026-03-05",
      status: "Open" as const,
      blocking: true,
      rationale: `${tie.name} is failing at ${tie.variancePct.toFixed(2)}% vs tolerance ${tie.tolerancePct.toFixed(2)}%.`,
      sourceTab: "risk-assessment" as const,
      sourceId: tie.name,
      sourceLabel: tie.name,
      sourceUrl: `/risk-assessment?focus=tieout&name=${encodeURIComponent(tie.name)}`,
    })),
    ...warnTieOuts.slice(0, 2).map((tie, idx) => ({
      id: `dq-risk-warn-${idx + 1}`,
      title: `Tighten warning tie-out: ${tie.name}`,
      impactArea: "Risk / Tie-out",
      impactScore: Number((78 - idx * 3).toFixed(1)),
      owner: "Deal Team",
      dueDate: "2026-03-06",
      status: "In Progress" as const,
      blocking: idx === 0,
      rationale: `${tie.name} sits in warning band at ${tie.variancePct.toFixed(2)}%.`,
      sourceTab: "risk-assessment" as const,
      sourceId: tie.name,
      sourceLabel: tie.name,
      sourceUrl: `/risk-assessment?focus=tieout&name=${encodeURIComponent(tie.name)}`,
    })),
    ...blockingInquiries.slice(0, 3).map((inq, idx) => ({
      id: `dq-inquiry-${idx + 1}`,
      title: `Close blocking inquiry: ${inq.request}`,
      impactArea: "Inquiry / Readiness",
      impactScore: Number((88 - idx * 5).toFixed(1)),
      owner: inq.owner,
      dueDate: inq.dueDate,
      status: inq.status === "In Progress" ? ("In Progress" as const) : ("Open" as const),
      blocking: true,
      rationale: "Blocking inquiry directly gates report readiness and IC package quality.",
      sourceTab: "inquiry" as const,
      sourceId: inq.id,
      sourceLabel: inq.id,
      sourceUrl: `/inquiry?focus=inquiry&id=${encodeURIComponent(inq.id)}`,
    })),
    ...highRiskAdjustments.map((adj, idx) => ({
      id: `dq-adjustment-${idx + 1}`,
      title: `Validate adjustment support: ${adj.id}`,
      impactArea: "QoE / Adjustments",
      impactScore: Number((72 - idx * 2).toFixed(1)),
      owner: "QoE Workstream Lead",
      dueDate: "2026-03-07",
      status: adj.status === "Reviewed" ? ("In Progress" as const) : ("Open" as const),
      blocking: idx === 0,
      rationale: `${adj.id} (${adj.status}) carries material impact of $${(adj.amount / 1_000_000).toFixed(2)}M.`,
      sourceTab: "financial-analysis" as const,
      sourceId: adj.id,
      sourceLabel: `${adj.id} - ${adj.category}`,
      sourceUrl: `/financial-analysis?sub=qoe&focus=adjustment&id=${encodeURIComponent(adj.id)}`,
    })),
    ...missingCoverage.map((gap, idx) => ({
      id: `dq-docs-${idx + 1}`,
      title: `Ingest missing document: ${gap.schedule} (${gap.month.month})`,
      impactArea: "Documents / Data Integrity",
      impactScore: Number((66 - idx * 2).toFixed(1)),
      owner: "Data Room Owner",
      dueDate: "2026-03-08",
      status: "Open" as const,
      blocking: idx === 0,
      rationale: `Coverage gap on ${gap.schedule} for ${gap.month.month} reduces confidence and traceability.`,
      sourceTab: "documents" as const,
      sourceId: `${gap.schedule}-${gap.month.month}`,
      sourceLabel: gap.schedule,
      sourceUrl: `/documents?focus=coverage&schedule=${encodeURIComponent(gap.schedule)}&month=${encodeURIComponent(gap.month.month)}`,
    })),
  ]
    .sort((a, b) => b.impactScore - a.impactScore)
    .slice(0, 10);

  const blockingCount = items.filter((item) => item.blocking).length;
  const tieOutFailCount = failTieOuts.length;
  const readiness: "Ready" | "Draft" | "Blocked" =
    blockingCount > 0 || tieOutFailCount > 0
      ? "Blocked"
      : risk.riskScore >= 5.5
        ? "Draft"
        : "Ready";

  return {
    lastUpdated: summary.lastUpdated,
    readiness,
    items,
  };
}
