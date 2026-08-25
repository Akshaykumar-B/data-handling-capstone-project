import type { Metadata, Viewport } from "next";
import { Inter, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";
import { DashboardShell } from "@/components/dashboard-shell";
import { Providers } from "./providers";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const ibmPlexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-mono-ibm",
});

export const metadata: Metadata = {
  title: {
    default: "Public Transit Dashboard",
    template: "%s · Public Transit Dashboard",
  },
  description:
    "A Phase 5 analytics dashboard for NYC bus ridership, customer journey time performance, routes, and stop coverage, built from the Phase 3/4 processed data pipeline.",
};

export const viewport: Viewport = {
  themeColor: "#14181c",
  colorScheme: "light",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="bg-background">
      <body className={`${inter.variable} ${ibmPlexMono.variable} font-sans antialiased`}>
        <Providers>
          <DashboardShell>{children}</DashboardShell>
        </Providers>
      </body>
    </html>
  );
}
