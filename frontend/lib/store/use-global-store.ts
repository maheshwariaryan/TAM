"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

type Period = "Monthly" | "Quarterly" | "Annual";
type Basis = "Reported" | "Normalized" | "Pro Forma";

type GlobalState = {
  deal: string;
  dealId: string | null;      // real UUID from the FDD backend
  period: Period;
  basis: Basis;
  selectedMetricId: string | null;
  reportDraft: string[];
  notes: string;
  setDeal: (deal: string) => void;
  setDealId: (id: string | null) => void;
  setActiveDeal: (deal: string, dealId: string) => void;
  setPeriod: (period: Period) => void;
  setBasis: (basis: Basis) => void;
  setSelectedMetricId: (id: string | null) => void;
  addReportDraft: (snippet: string) => void;
  setReportDraft: (snippets: string[]) => void;
  setNotes: (value: string) => void;
};

export const useGlobalStore = create<GlobalState>()(
  persist(
    (set, get) => ({
      deal: "",
      dealId: null,
      period: "Monthly",
      basis: "Reported",
      selectedMetricId: null,
      reportDraft: [],
      notes: "",
      setDeal: (deal) => set({ deal }),
      setDealId: (dealId) => set({ dealId }),
      setActiveDeal: (deal, dealId) => set({ deal, dealId }),
      setPeriod: (period) => set({ period }),
      setBasis: (basis) => set({ basis }),
      setSelectedMetricId: (selectedMetricId) => set({ selectedMetricId }),
      addReportDraft: (snippet) => {
        const current = get().reportDraft;
        set({ reportDraft: [...current, snippet] });
      },
      setReportDraft: (snippets) => set({ reportDraft: snippets }),
      setNotes: (value) => set({ notes: value }),
    }),
    { name: "tam-global-state" }
  )
);
