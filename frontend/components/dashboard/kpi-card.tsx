import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

type KpiCardProps = {
  label: string;
  value: string;
  detail?: string;
  accent?: "primary" | "accent" | "neutral";
  className?: string;
};

const accentClass: Record<NonNullable<KpiCardProps["accent"]>, string> = {
  primary: "border-t-primary",
  accent: "border-t-accent",
  neutral: "border-t-border",
};

export function KpiCard({ label, value, detail, accent = "neutral", className }: KpiCardProps) {
  return (
    <Card className={cn("gap-2 rounded-md border-t-4 py-5", accentClass[accent], className)}>
      <CardHeader className="gap-1 px-5">
        <CardDescription className="font-mono text-[11px] tracking-wide text-muted-foreground uppercase">{label}</CardDescription>
        <CardTitle className="font-mono text-3xl font-semibold tabular-nums">{value}</CardTitle>
      </CardHeader>
      {detail ? (
        <CardContent className="px-5">
          <p className="text-sm leading-relaxed text-muted-foreground">{detail}</p>
        </CardContent>
      ) : null}
    </Card>
  );
}
