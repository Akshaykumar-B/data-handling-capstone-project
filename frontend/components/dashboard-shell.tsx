"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { apiClient } from "../lib/api-client";

const navigation = [
  ["/overview", "Overview"], ["/ridership", "Ridership"], ["/cjtp", "CJTP"],
  ["/routes-stops", "Routes + Stops"], ["/relationships", "Relationships"],
  ["/data-quality", "Data quality"], ["/about", "About"],
];

export function DashboardShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [apiState, setApiState] = useState("Checking API");
  useEffect(() => {
    if (!process.env.NEXT_PUBLIC_API_BASE_URL) { setApiState("API URL not configured"); return; }
    Promise.all([apiClient.health(), apiClient.dataStatus()]).then(([, data]) => {
      setApiState(data.status === "ready" ? "API + data ready" : "API online · data incomplete");
    }).catch(() => setApiState("API unavailable"));
  }, []);
  return <div className="shell">
    <aside className="sidebar"><div className="brand"><span className="brand-mark">MTA</span><span>Transit intelligence</span></div>
      <nav aria-label="Dashboard navigation">{navigation.map(([href, label]) => <Link className={pathname === href ? "active" : ""} href={href} key={href}>{label}</Link>)}</nav>
      <div className="api-status" aria-live="polite"><span className="status-dot" />{apiState}</div>
    </aside>
    <main className="main"><header><span className="eyebrow">PUBLIC TRANSIT / PHASE 5</span><h1>Route performance dashboard</h1></header>{children}</main>
  </div>;
}