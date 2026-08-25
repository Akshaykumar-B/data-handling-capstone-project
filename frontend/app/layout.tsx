import type { Metadata } from "next";
import "./globals.css";
import { DashboardShell } from "../components/dashboard-shell";

export const metadata: Metadata = { title: "Public Transit Dashboard" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><DashboardShell>{children}</DashboardShell></body></html>;
}