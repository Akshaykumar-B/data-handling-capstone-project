import { Info } from "lucide-react";
import type { RouteCoverage } from "@/lib/api-client";

type CoverageNoteProps = {
  source: string;
  coverage?: RouteCoverage | null;
  limitations?: string[];
  className?: string;
};

/**
 * Renders each endpoint's `meta.source` / `meta.coverage` / `meta.limitations`
 * so every chart is traceable to the underlying processed dataset and its
 * documented gaps, per the project's "never fabricate" constraint.
 */
export function CoverageNote({ source, coverage, limitations, className }: CoverageNoteProps) {
  const hasLimitations = limitations && limitations.length > 0;
  return (
    <div className={`flex flex-col gap-1.5 border-t border-dashed pt-3 text-xs leading-relaxed text-muted-foreground ${className ?? ""}`}>
      <p className="flex items-start gap-1.5">
        <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden />
        <span>
          Source: <span className="font-mono">{source}</span>
          {coverage ? (
            <>
              {" "}
              &middot; route coverage {coverage.matching_route_count}/{coverage.project_route_count} (
              {coverage.coverage_percentage.toFixed(1)}%)
            </>
          ) : null}
        </span>
      </p>
      {hasLimitations
        ? limitations.map((limitation) => (
            <p key={limitation} className="pl-5">
              {limitation}
            </p>
          ))
        : null}
    </div>
  );
}
