"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { FileText, RefreshCw, Download } from "lucide-react";

interface Section {
  title: string;
  body: string;
}

const PLACEHOLDER_SECTIONS: Section[] = [
  {
    title: "Executive Summary",
    body:
      "This report provides a preliminary financial due diligence summary for the subject company. Revenue trends appear stable over the trailing 36-month period with consistent gross margin expansion. Adjusted EBITDA reflects several addbacks under review — primarily owner compensation normalisation and a one-time legal settlement. The business demonstrates recurring revenue characteristics suitable for further quality-of-earnings scrutiny.",
  },
  {
    title: "Key Risks",
    body:
      "1. Owner compensation is materially above industry benchmarks and requires normalisation confirmation from management. 2. A related-party transaction flagged in the GL warrants additional diligence on arm's-length pricing. 3. AR days are trending upward over the last two quarters, which may indicate collection pressure or revenue-recognition timing issues. 4. EBITDA margin volatility in Q3 of the prior year has not been fully explained by management commentary.",
  },
  {
    title: "Quality of Earnings Highlights",
    body:
      "Adjusted EBITDA is higher than reported EBITDA after applying normalisation addbacks. The four planted adjustments (management fees, legal settlement, R&D reclassification, one-time marketing spend) account for the bridge. Waterfall arithmetic has been verified and closes within tolerance. LTM adjusted EBITDA is considered a reasonable proxy for sustainable earnings, pending confirmation of the addback rationale.",
  },
  {
    title: "Preliminary Recommendation",
    body:
      "Proceed to Phase 2 diligence. Priority areas: (a) confirm owner-comp normalisation with payroll records, (b) obtain related-party contract documentation, (c) request AR ageing reconciliation for the last four quarters, (d) validate the legal settlement as truly non-recurring. No deal-breaking issues identified at this stage. Valuation multiple range to be refined after Phase 2 findings.",
  },
];

interface Props {
  dealId: string | null | undefined;
  deal: string;
}

export function JuniorAnalystReport({ dealId, deal }: Props) {
  const [regenerating, setRegenerating] = useState(false);
  const [generatedAt] = useState(() => new Date().toLocaleString());

  const handleRegenerate = async () => {
    setRegenerating(true);
    // Agent call will go here once LLM logic is wired
    await new Promise((r) => setTimeout(r, 1800));
    setRegenerating(false);
  };

  if (!dealId) {
    return (
      <Card className="border-dashed">
        <CardContent className="flex flex-col items-center justify-center gap-2 py-10 text-center">
          <FileText className="h-8 w-8 text-muted-foreground/50" />
          <p className="text-sm font-medium text-muted-foreground">Junior Analyst Summary Report</p>
          <p className="text-xs text-muted-foreground">Upload and process a deal to generate the analyst report.</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5 text-cyan-500" />
              Junior Analyst Summary Report
            </CardTitle>
            <p className="mt-1 text-xs text-muted-foreground">
              {deal} &nbsp;·&nbsp; Generated {generatedAt} &nbsp;·&nbsp;{" "}
              <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-semibold text-amber-700 dark:bg-amber-900/40 dark:text-amber-400">
                AI Draft — Requires Analyst Review
              </span>
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={handleRegenerate}
              disabled={regenerating}
            >
              <RefreshCw className={`mr-1 h-3.5 w-3.5 ${regenerating ? "animate-spin" : ""}`} />
              {regenerating ? "Regenerating…" : "Regenerate"}
            </Button>
            <Button size="sm" variant="outline" disabled title="PDF export coming soon">
              <Download className="mr-1 h-3.5 w-3.5" />
              Export PDF
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid gap-4 md:grid-cols-2">
          {PLACEHOLDER_SECTIONS.map((section) => (
            <div key={section.title} className="rounded-lg border bg-muted/30 p-4">
              <h3 className="mb-2 text-sm font-semibold">{section.title}</h3>
              <p className="text-sm leading-relaxed text-muted-foreground">{section.body}</p>
            </div>
          ))}
        </div>
        <p className="mt-4 text-[11px] text-muted-foreground/60">
          This report is auto-generated by the TAM Junior Analyst Agent and has not been reviewed by a senior analyst.
          It is intended as a first-pass summary only. Agent logic and source attribution will be wired in a future release.
        </p>
      </CardContent>
    </Card>
  );
}
