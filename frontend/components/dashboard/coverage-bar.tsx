import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatPercent } from "@/lib/format";

export function CoverageBar({
  label,
  matching,
  total,
  percentage,
  missing,
}: {
  label: string;
  matching: number;
  total: number;
  percentage: number;
  missing?: string[];
}) {
  return (
    <Card className="gap-3 py-5">
      <CardHeader className="gap-1 px-5">
        <CardTitle className="text-sm font-medium">{label}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-2 px-5">
        <div className="flex items-baseline justify-between">
          <span className="font-mono text-xl font-semibold tabular-nums">
            {matching}/{total}
          </span>
          <span className="text-sm text-muted-foreground">{formatPercent(percentage)}</span>
        </div>
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
          <div className="h-full rounded-full bg-primary" style={{ width: `${Math.min(100, percentage)}%` }} />
        </div>
        {missing && missing.length > 0 ? (
          <p className="text-xs leading-relaxed text-muted-foreground">
            {missing.length} route{missing.length === 1 ? "" : "s"} absent, not fabricated: {missing.slice(0, 8).join(", ")}
            {missing.length > 8 ? "…" : ""}
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}
