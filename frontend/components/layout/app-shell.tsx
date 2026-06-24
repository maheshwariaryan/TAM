"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Menu, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import { cn } from "@/lib/utils/cn";
import { useGlobalStore } from "@/lib/store/use-global-store";
import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { TamLlmSidebar } from "@/components/dashboard/tam-llm-sidebar";
import { ThemeToggle } from "@/components/layout/theme-toggle";
import { listDeals, type Deal } from "@/lib/api/fdd-client";

const navItems = [
  { label: "Executive Summary", href: "/dashboard" },
  { label: "Upload Deal Data", href: "/upload" },
  { label: "Financial Analysis", href: "/financial-analysis" },
  { label: "Risk Assessment", href: "/risk-assessment" },
  { label: "Customer Analytics", href: "/customer-analytics" },
  { label: "Documents", href: "/documents" },
  { label: "Inquiry", href: "/inquiry" },
  { label: "Notes", href: "/notes" },
  { label: "Reports", href: "/reports" },
  { label: "Settings", href: "/settings" },
];

function SideNav({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <aside className="flex h-full flex-col gap-1 p-3">
      <div className="mb-3 rounded-lg bg-primary p-3 text-primary-foreground shadow-soft">
        <p className="text-xs uppercase tracking-[0.18em]">TAM</p>
        <h1 className="text-lg font-semibold">Due Diligence OS</h1>
      </div>
      {navItems.map((item) => (
        <Link
          key={item.href}
          href={item.href}
          onClick={onNavigate}
          className={cn(
            "rounded-md px-3 py-2 text-sm font-medium text-foreground/85 hover:bg-muted",
            pathname === item.href && "bg-secondary text-foreground"
          )}
        >
          {item.label}
        </Link>
      ))}
    </aside>
  );
}

function Topbar() {
  const router = useRouter();
  const { dealId, setActiveDeal } = useGlobalStore();
  const [deals, setDeals] = useState<Deal[]>([]);

  // Load deals from backend on mount and whenever the page focuses
  useEffect(() => {
    const load = () => {
      listDeals()
        .then((data) => {
          setDeals(data);
          // Auto-select first deal if none is selected or current is stale
          if (data.length > 0 && !data.find((d) => d.deal_id === dealId)) {
            setActiveDeal(
              `${data[0].company_name} — ${data[0].deal_name}`,
              data[0].deal_id
            );
          }
        })
        .catch(() => setDeals([]));
    };
    load();
    window.addEventListener("focus", load);
    return () => window.removeEventListener("focus", load);
  }, [dealId, setActiveDeal]);

  const handleDealChange = (id: string) => {
    const selected = deals.find((d) => d.deal_id === id);
    if (selected) {
      setActiveDeal(`${selected.company_name} — ${selected.deal_name}`, selected.deal_id);
    }
  };

  return (
    <div className="sticky top-0 z-30 flex flex-wrap items-center gap-2 border-b bg-background/90 px-3 py-3 backdrop-blur">
      <div className="mr-auto text-sm font-semibold">Analyst Workspace</div>

      {deals.length === 0 ? (
        <span className="text-sm text-muted-foreground">No deals — upload data first</span>
      ) : (
        <select
          aria-label="Deal selector"
          value={dealId ?? ""}
          onChange={(e) => handleDealChange(e.target.value)}
          className="rounded-md border border-border bg-card px-2 py-1 text-sm text-foreground"
        >
          {deals.map((d) => (
            <option key={d.deal_id} value={d.deal_id}>
              {d.company_name} — {d.deal_name}
            </option>
          ))}
        </select>
      )}

      <Button size="sm" variant="outline" onClick={() => router.push("/upload")}>
        <Upload className="mr-1 h-4 w-4" /> New Deal
      </Button>
      <ThemeToggle />
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const noShellRoutes = ["/welcome", "/login", "/signup", "/onboarding"];
  const hideShell = noShellRoutes.some((r) => pathname === r || pathname.startsWith(`${r}/`));

  if (hideShell) return <>{children}</>;

  return (
    <div className="tam-gradient min-h-screen">
      <div className="mx-auto flex w-full max-w-[1600px]">
        <div className="hidden min-h-screen w-64 shrink-0 border-r bg-card/90 md:block">
          <SideNav />
        </div>
        <div className="w-full">
          <div className="border-b bg-card px-3 py-2 md:hidden">
            <Sheet open={open} onOpenChange={setOpen}>
              <SheetTrigger asChild>
                <Button variant="outline" size="sm">
                  <Menu className="mr-1 h-4 w-4" /> Menu
                </Button>
              </SheetTrigger>
              <SheetContent>
                <SideNav onNavigate={() => setOpen(false)} />
              </SheetContent>
            </Sheet>
          </div>
          <Topbar />
          <main className="p-4 md:p-6">{children}</main>
          <TamLlmSidebar />
        </div>
      </div>
    </div>
  );
}
