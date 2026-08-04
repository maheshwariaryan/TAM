"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useGlobalStore } from "@/lib/store/use-global-store";
import { getDealSettings, updateDealSettings, type DealSettings } from "@/lib/api/fdd-client";

const DEFAULTS: DealSettings = {
  materiality_threshold: 75000,
  tie_out_tolerance_pct: 0.5,
  cash_conversion_medium_pct: 60,
  cash_conversion_high_pct: 30,
  cash_conversion_critical_pct: 0,
};

export default function SettingsPage() {
  const { dealId } = useGlobalStore();
  const [materiality, setMateriality] = useState(String(DEFAULTS.materiality_threshold));
  const [tolerance, setTolerance] = useState(String(DEFAULTS.tie_out_tolerance_pct));
  const [conv60, setConv60] = useState(String(DEFAULTS.cash_conversion_medium_pct));
  const [conv30, setConv30] = useState(String(DEFAULTS.cash_conversion_high_pct));
  const [conv0, setConv0] = useState(String(DEFAULTS.cash_conversion_critical_pct));
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!dealId) return;
    setLoading(true);
    setError(null);
    getDealSettings(dealId)
      .then((s) => {
        setMateriality(String(s.materiality_threshold));
        setTolerance(String(s.tie_out_tolerance_pct));
        setConv60(String(s.cash_conversion_medium_pct));
        setConv30(String(s.cash_conversion_high_pct));
        setConv0(String(s.cash_conversion_critical_pct));
      })
      .catch(() => {
        // No saved settings yet — keep today's defaults.
      })
      .finally(() => setLoading(false));
  }, [dealId]);

  const handleSave = async () => {
    if (!dealId) {
      setError("Select a deal before saving settings.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await updateDealSettings(dealId, {
        materiality_threshold: Number(materiality),
        tie_out_tolerance_pct: Number(tolerance),
        cash_conversion_medium_pct: Number(conv60),
        cash_conversion_high_pct: Number(conv30),
        cash_conversion_critical_pct: Number(conv0),
      });
      setSavedAt(new Date().toLocaleString());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save settings.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-5">
      <h2 className="text-xl font-semibold">Settings</h2>
      <Card>
        <CardHeader><CardTitle>Configurable parameters</CardTitle></CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-2">
          <label className="text-sm">Materiality threshold ($)<input value={materiality} onChange={(e) => setMateriality(e.target.value)} disabled={loading} className="mt-1 w-full rounded border px-2 py-1" /></label>
          <label className="text-sm">Tie-out tolerance %<input value={tolerance} onChange={(e) => setTolerance(e.target.value)} disabled={loading} className="mt-1 w-full rounded border px-2 py-1" /></label>
          <label className="text-sm">Cash conversion threshold (&lt;60)<input value={conv60} onChange={(e) => setConv60(e.target.value)} disabled={loading} className="mt-1 w-full rounded border px-2 py-1" /></label>
          <label className="text-sm">Cash conversion threshold (&lt;30)<input value={conv30} onChange={(e) => setConv30(e.target.value)} disabled={loading} className="mt-1 w-full rounded border px-2 py-1" /></label>
          <label className="text-sm">Cash conversion threshold (&lt;0)<input value={conv0} onChange={(e) => setConv0(e.target.value)} disabled={loading} className="mt-1 w-full rounded border px-2 py-1" /></label>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Mapping Studio (placeholder)</CardTitle></CardHeader>
        <CardContent className="text-sm text-muted-foreground">In the next phase, this section will include mapping dictionaries, account-rule templates, and governance workflows.</CardContent>
      </Card>
      <div className="space-y-1">
        <Button onClick={handleSave} disabled={saving}>{saving ? "Saving..." : "Save configuration"}</Button>
        {savedAt ? <p className="text-xs text-muted-foreground">Saved at {savedAt}</p> : null}
        {error ? <p className="text-xs text-destructive">{error}</p> : null}
      </div>
    </div>
  );
}
