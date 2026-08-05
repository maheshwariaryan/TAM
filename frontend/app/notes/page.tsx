"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useGlobalStore } from "@/lib/store/use-global-store";
import { getNotes, saveNotes } from "@/lib/api/fdd-client";

export default function NotesPage() {
  const { dealId, notes, setNotes, addReportDraft, setReportDraft, reportDraft } = useGlobalStore();
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(false);

  // Deal-scoped notes are loaded fresh whenever the active deal changes, overwriting
  // whatever the (non-deal-scoped) global store currently holds from a prior deal.
  useEffect(() => {
    if (!dealId) return;
    setLoading(true);
    getNotes(dealId)
      .then((saved) => {
        setNotes(saved.notes);
        setReportDraft(saved.report_draft);
      })
      .catch(() => {
        // No saved notes yet (or the request failed) — leave current state as-is.
      })
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dealId]);

  const handleSave = async () => {
    if (!dealId) {
      // No active deal — nothing to persist to, keep today's local-only behavior.
      setSavedAt(new Date().toLocaleString());
      return;
    }
    setSaving(true);
    try {
      await saveNotes(dealId, notes, reportDraft);
      setSavedAt(new Date().toLocaleString());
    } catch {
      // Leave savedAt unset so the lack of confirmation is visible; button stays usable to retry.
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-5">
      <h2 className="text-xl font-semibold">Notes</h2>
      <Card>
        <CardHeader><CardTitle>Analyst Notes</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <Textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Capture assumptions, management commentary, and unresolved tie-outs..."
            disabled={loading}
          />
          <div className="flex gap-2">
            <Button onClick={handleSave} disabled={saving}>{saving ? "Saving..." : "Save"}</Button>
            <Button variant="outline" onClick={() => {
              const selected = typeof window !== "undefined" ? window.getSelection()?.toString() : "";
              if (selected) addReportDraft(selected);
            }}>Add selected text to Report Narrative</Button>
          </div>
          {savedAt ? <p className="text-xs text-muted-foreground">Saved at {savedAt}</p> : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Report Draft Snippets</CardTitle></CardHeader>
        <CardContent className="space-y-2">
          {reportDraft.length === 0 ? <p className="text-sm text-muted-foreground">No methodology snippets yet.</p> : reportDraft.map((snippet, i) => (
            <div key={i} className="rounded border bg-card p-2 text-sm">{snippet}</div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
