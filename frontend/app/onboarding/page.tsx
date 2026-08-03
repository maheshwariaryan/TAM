"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Sparkles, Cpu, Database, ShieldCheck, BarChart3 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { DocumentUploadTool } from "@/components/documents/document-upload-tool";
import { FileInventorySchema } from "@/lib/schemas/types";
import { z } from "zod";
import { useGlobalStore } from "@/lib/store/use-global-store";

const walkthrough = [
  {
    icon: Database,
    title: "Document Intelligence",
    body: "TAM classifies schedules, coverage periods, and confidence while surfacing missing PBC items automatically.",
  },
  {
    icon: Cpu,
    title: "Financial Build Engine",
    body: "The system standardizes statements, computes QoE adjustments, ties out TB/GL/aging, and builds metric lineage.",
  },
  {
    icon: BarChart3,
    title: "Analyst-Grade Insights",
    body: "You get interactive dashboards for QoE, working capital, conversion, customer quality, and risk concentration.",
  },
  {
    icon: ShieldCheck,
    title: "Defensibility & Trace",
    body: "Every KPI and chart can be traced back through formulas, sources, and review-ready cell-level references.",
  },
];

const loadingStages = [
  "Mapping chart of accounts...",
  "Reconciling tie-outs across TB, GL, and schedules...",
  "Running anomaly detection and risk scoring...",
  "Constructing QoE and cash conversion models...",
  "Generating insights and presentation layer...",
];

export default function OnboardingPage() {
  const router = useRouter();
  const { setDeal } = useGlobalStore();
  const [uploadedFiles, setUploadedFiles] = useState<z.infer<typeof FileInventorySchema>[]>([]);
  const [analyzing, setAnalyzing] = useState(false);
  const [stageIndex, setStageIndex] = useState(0);
  const [companyName, setCompanyName] = useState("");
  const [sector, setSector] = useState("");
  const [subSector, setSubSector] = useState("");
  const [hqRegion, setHqRegion] = useState("");
  const [currency, setCurrency] = useState("USD");
  const [fiscalYearEnd, setFiscalYearEnd] = useState("");

  useEffect(() => {
    const raw = window.localStorage.getItem("tam-uploaded-files");
    if (!raw) return;
    try {
      setUploadedFiles(JSON.parse(raw));
    } catch {
      setUploadedFiles([]);
    }
  }, []);

  useEffect(() => {
    const raw = window.localStorage.getItem("tam-company-profile-draft");
    if (!raw) return;
    try {
      const parsed = JSON.parse(raw) as {
        companyName?: string;
        sector?: string;
        subSector?: string;
        hqRegion?: string;
        currency?: string;
        fiscalYearEnd?: string;
      };
      setCompanyName(parsed.companyName ?? "");
      setSector(parsed.sector ?? "");
      setSubSector(parsed.subSector ?? "");
      setHqRegion(parsed.hqRegion ?? "");
      setCurrency(parsed.currency ?? "USD");
      setFiscalYearEnd(parsed.fiscalYearEnd ?? "");
    } catch {
      // ignore parse issues
    }
  }, []);

  useEffect(() => {
    window.localStorage.setItem(
      "tam-company-profile-draft",
      JSON.stringify({ companyName, sector, subSector, hqRegion, currency, fiscalYearEnd })
    );
  }, [companyName, sector, subSector, hqRegion, currency, fiscalYearEnd]);

  useEffect(() => {
    if (!analyzing) return;
    const stageTimer = setInterval(() => {
      setStageIndex((prev) => (prev + 1) % loadingStages.length);
    }, 1400);
    const completeTimer = setTimeout(() => {
      try {
        const profile = {
          id: `cmp-${Date.now()}`,
          companyName: companyName.trim(),
          sector,
          subSector,
          hqRegion,
          currency,
          fiscalYearEnd,
          uploadedAt: new Date().toISOString(),
        };
        const previous = window.localStorage.getItem("tam-company-profiles");
        const parsed = previous ? (JSON.parse(previous) as typeof profile[]) : [];
        const merged = [profile, ...parsed.filter((p) => p.companyName !== profile.companyName)];
        window.localStorage.setItem("tam-company-profiles", JSON.stringify(merged));
        setDeal(profile.companyName || "Project Atlas");
      } finally {
        router.push("/upload");
        router.refresh();
      }
    }, 8200);
    return () => {
      clearInterval(stageTimer);
      clearTimeout(completeTimer);
    };
  }, [analyzing, companyName, currency, fiscalYearEnd, hqRegion, router, sector, setDeal, subSector]);

  const summary = useMemo(() => {
    if (!uploadedFiles.length) return "No files uploaded yet";
    const uniqueTypes = new Set(uploadedFiles.map((f) => f.detectedType));
    return `${uploadedFiles.length} file(s), ${uniqueTypes.size} detected schedule type(s)`;
  }, [uploadedFiles]);
  const stageProgress = ((stageIndex + 1) / loadingStages.length) * 100;
  const hasRequiredCompanyFields = companyName.trim().length > 1 && sector.trim().length > 1;
  const uploadStorageKey = companyName.trim().length > 1 ? `tam-uploaded-files:${companyName.trim()}` : "tam-uploaded-files";

  return (
    <div className="relative min-h-screen overflow-hidden bg-slate-950 px-6 py-10 text-slate-100">
      <div className="absolute inset-0 tam-grid opacity-45" />
      <div className="absolute inset-0 tam-background-flow opacity-45" />
      <div className="absolute -left-24 top-28 h-80 w-80 rounded-full bg-cyan-400/20 blur-3xl tam-float" />
      <div className="absolute -right-20 bottom-16 h-72 w-72 rounded-full bg-emerald-400/20 blur-3xl tam-float" style={{ animationDuration: "9s", animationDelay: "0.8s" }} />
      <div className="pointer-events-none absolute inset-0">
        {Array.from({ length: 14 }).map((_, idx) => (
          <span
            key={idx}
            className="absolute h-2 w-2 rounded-full bg-cyan-200/35 tam-particle"
            style={{
              left: `${6 + ((idx * 7) % 88)}%`,
              top: `${8 + ((idx * 13) % 80)}%`,
              animationDelay: `${idx * 0.35}s`,
              animationDuration: `${6 + (idx % 5)}s`,
            }}
          />
        ))}
      </div>

      <div className="relative mx-auto max-w-7xl space-y-6">
        <div className="tam-fade-up rounded-2xl border border-white/20 bg-white/10 p-6 backdrop-blur-xl">
          <p className="text-xs uppercase tracking-[0.2em] text-cyan-200">TAM Intake Workspace</p>
          <h1 className="mt-2 text-3xl font-semibold">Upload deal documents and launch analysis</h1>
          <p className="mt-3 max-w-3xl text-sm text-slate-200">
            Upload your files first. TAM will parse and map them, build due diligence metrics, run tie-out and anomaly checks,
            then bring you into the full analyst dashboard.
          </p>
        </div>

        <div className="grid gap-5 xl:grid-cols-5">
          <div className="xl:col-span-3">
            <Card className="mb-5 border-white/20 bg-white/10 text-white backdrop-blur-xl">
              <CardHeader><CardTitle>Company Intake Details</CardTitle></CardHeader>
              <CardContent className="grid gap-3 md:grid-cols-2">
                <label className="text-sm">
                  Company Name *
                  <input value={companyName} onChange={(e) => setCompanyName(e.target.value)} placeholder="Acme Software Inc." className="mt-1 w-full rounded-md border border-white/25 bg-white/10 px-3 py-2 outline-none focus:border-cyan-300" />
                </label>
                <label className="text-sm">
                  Sector *
                  <input value={sector} onChange={(e) => setSector(e.target.value)} placeholder="Technology / SaaS" className="mt-1 w-full rounded-md border border-white/25 bg-white/10 px-3 py-2 outline-none focus:border-cyan-300" />
                </label>
                <label className="text-sm">
                  Sub-Sector
                  <input value={subSector} onChange={(e) => setSubSector(e.target.value)} placeholder="Vertical SaaS" className="mt-1 w-full rounded-md border border-white/25 bg-white/10 px-3 py-2 outline-none focus:border-cyan-300" />
                </label>
                <label className="text-sm">
                  HQ / Region
                  <input value={hqRegion} onChange={(e) => setHqRegion(e.target.value)} placeholder="North America" className="mt-1 w-full rounded-md border border-white/25 bg-white/10 px-3 py-2 outline-none focus:border-cyan-300" />
                </label>
                <label className="text-sm">
                  Reporting Currency
                  <select value={currency} onChange={(e) => setCurrency(e.target.value)} className="mt-1 w-full rounded-md border border-white/25 bg-white/10 px-3 py-2 outline-none focus:border-cyan-300">
                    <option className="text-slate-900">USD</option>
                    <option className="text-slate-900">EUR</option>
                    <option className="text-slate-900">GBP</option>
                    <option className="text-slate-900">INR</option>
                    <option className="text-slate-900">CAD</option>
                  </select>
                </label>
                <label className="text-sm">
                  Fiscal Year End
                  <input value={fiscalYearEnd} onChange={(e) => setFiscalYearEnd(e.target.value)} placeholder="Dec-31" className="mt-1 w-full rounded-md border border-white/25 bg-white/10 px-3 py-2 outline-none focus:border-cyan-300" />
                </label>
              </CardContent>
            </Card>
            <DocumentUploadTool
              entityName={companyName}
              onFilesProcessed={(rows) => {
                setUploadedFiles((prev) => {
                  const next = [...rows, ...prev];
                  const dedup = next.filter((row, idx, arr) => arr.findIndex((x) => x.file === row.file) === idx);
                  window.localStorage.setItem(uploadStorageKey, JSON.stringify(dedup));
                  window.localStorage.setItem("tam-uploaded-files", JSON.stringify(dedup));
                  return dedup;
                });
              }}
            />
          </div>

          <div className="xl:col-span-2 space-y-4">
            <Card className="border-white/20 bg-white/10 text-white backdrop-blur-xl">
              <CardHeader>
                <CardTitle className="flex items-center gap-2"><Sparkles className="h-4 w-4 text-cyan-300" /> TAM Walkthrough</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {walkthrough.map((item, idx) => {
                  const Icon = item.icon;
                  return (
                    <div key={item.title} className="tam-fade-up rounded-lg border border-white/20 bg-white/5 p-3" style={{ animationDelay: `${idx * 120}ms` }}>
                      <p className="mb-1 inline-flex items-center gap-2 text-sm font-semibold"><Icon className="h-4 w-4 text-cyan-200" />{item.title}</p>
                      <p className="text-xs text-slate-200">{item.body}</p>
                    </div>
                  );
                })}
              </CardContent>
            </Card>

            <Card className="border-white/20 bg-white/10 text-white backdrop-blur-xl">
              <CardHeader><CardTitle>Upload Status</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                <p className="text-sm text-slate-200">{summary}</p>
                {!hasRequiredCompanyFields ? <p className="text-xs text-amber-200">Add Company Name and Sector to continue.</p> : null}
                <Button className="w-full" disabled={!hasRequiredCompanyFields || uploadedFiles.length === 0 || analyzing} onClick={() => setAnalyzing(true)}>
                  {analyzing ? "Generating analysis..." : "Generate Analysis"}
                </Button>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>

      {analyzing ? (
        <div className="fixed inset-0 z-[90] flex items-center justify-center bg-slate-950/90 px-6">
          <div className="w-full max-w-2xl rounded-2xl border border-cyan-300/30 bg-slate-900/80 p-7 backdrop-blur">
            <p className="text-xs uppercase tracking-[0.2em] text-cyan-200">TAM Neural Analysis Engine</p>
            <h2 className="mt-2 text-2xl font-semibold">Building your due diligence intelligence stack</h2>

            <div className="mt-5 rounded-2xl border border-cyan-300/35 bg-black/40 p-4">
              <div className="mb-2 flex items-center justify-between text-[11px] uppercase tracking-[0.16em] text-cyan-200/90">
                <span>Pipeline Throughput</span>
                <span>{Math.round(stageProgress)}%</span>
              </div>
              <div className="relative h-3 overflow-hidden rounded-full bg-slate-700/90">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-cyan-400 via-sky-300 to-emerald-300 transition-[width] duration-700 ease-out"
                  style={{ width: `${stageProgress}%` }}
                />
                <div className="pointer-events-none absolute inset-0 tam-loading-scan" />
              </div>
              <div className="mt-4 h-2 overflow-hidden rounded-full bg-slate-800/90">
                <div className="h-full tam-loading-bar bg-gradient-to-r from-cyan-400 via-emerald-400 to-sky-300" />
              </div>
              <div className="mt-4 flex items-center gap-2">
                <span className="tam-loading-dot" />
                <span className="tam-loading-dot" style={{ animationDelay: "0.2s" }} />
                <span className="tam-loading-dot" style={{ animationDelay: "0.4s" }} />
                <p className="text-xs text-slate-300">Crunching trial balance, ledgers, tie-outs, and anomaly checks...</p>
              </div>
            </div>

            <div className="mt-6 grid gap-3 md:grid-cols-5">
              {loadingStages.map((stage, idx) => (
                <div key={stage} className={`rounded border p-2 text-xs ${idx === stageIndex ? "border-cyan-300 bg-cyan-400/15" : "border-slate-700 bg-slate-900/60"}`}>
                  {stage}
                </div>
              ))}
            </div>

            <p className="mt-5 text-sm text-cyan-100">{loadingStages[stageIndex]}</p>
            <p className="mt-1 text-xs text-slate-300">Please stay on this screen. You will be redirected to the dashboard once analysis is complete.</p>
          </div>
        </div>
      ) : null}
    </div>
  );
}
