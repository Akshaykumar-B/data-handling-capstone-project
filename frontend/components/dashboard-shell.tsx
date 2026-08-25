"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { useDataStatus, useHealth } from "@/lib/queries";
import { isApiConfigured } from "@/lib/api-client";

const navigation = [
  { href: "/overview", label: "Overview" },
  { href: "/ridership", label: "Ridership" },
  { href: "/cjtp", label: "CJTP" },
  { href: "/routes-stops", label: "Routes + Stops" },
  { href: "/relationships", label: "Relationships" },
  { href: "/data-quality", label: "Data quality" },
  { href: "/about", label: "About" },
];

function ApiStatusIndicator() {
  const configured = isApiConfigured();
  const health = useHealth();
  const dataStatus = useDataStatus();

  let label = "API URL not configured";
  let tone: "ok" | "warn" | "error" = "warn";

  if (configured) {
    if (health.isLoading || dataStatus.isLoading) {
      label = "Checking API…";
      tone = "warn";
    } else if (health.isError || dataStatus.isError) {
      label = "API unavailable";
      tone = "error";
    } else if (dataStatus.data?.status === "ready") {
      label = "API + data ready";
      tone = "ok";
    } else {
      label = "API online · data incomplete";
      tone = "warn";
    }
  }

  const dotClass = { ok: "bg-emerald-400", warn: "bg-amber-400", error: "bg-red-400" }[tone];

  return (
    <div className="flex items-center gap-2 border-t border-sidebar-border px-3 py-3 font-mono text-[11px] text-sidebar-foreground/80" aria-live="polite">
      <span className={cn("size-1.5 shrink-0 rounded-full", dotClass)} aria-hidden />
      <span className="truncate">{label}</span>
    </div>
  );
}

export function DashboardShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <aside className="flex shrink-0 flex-col bg-sidebar text-sidebar-foreground md:w-60">
        <div className="flex items-center gap-2.5 px-4 py-5">
          <span className="route-chip bg-primary text-primary-foreground">MTA</span>
          <span className="text-sm font-semibold tracking-tight">Transit intelligence</span>
        </div>
        <nav aria-label="Dashboard navigation" className="flex flex-1 flex-col gap-0.5 px-2">
          {navigation.map((item) => {
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "rounded-sm border-l-2 border-transparent px-3 py-2 text-sm transition-colors",
                  active ? "border-sidebar-accent bg-white/5 font-medium text-white" : "text-sidebar-foreground/70 hover:bg-white/5 hover:text-sidebar-foreground",
                )}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
        <ApiStatusIndicator />
      </aside>
      <main className="flex-1">
        <div className="mx-auto flex max-w-6xl flex-col px-6 py-10 md:px-10">
          <header className="flex flex-col gap-1 border-b pb-6">
            <span className="font-mono text-[11px] tracking-[0.08em] text-muted-foreground uppercase">Public transit / Phase 5</span>
            <h1 className="text-3xl font-semibold tracking-tight text-balance md:text-4xl">Route performance dashboard</h1>
          </header>
          <div className="pt-8">{children}</div>
        </div>
      </main>
    </div>
  );
}
