import type { CorrelationPair, RidershipByDateRow, RidershipByRouteRow } from "@/lib/api-client";

/**
 * Views the real FastAPI contract doesn't expose directly. Every function
 * here derives strictly from fields already returned by
 * /ridership/routes and /ridership/daily &mdash; nothing is invented, and a
 * derivation never runs on an empty input.
 */

export type WeekdayWeekendPoint = { dayType: "Weekday" | "Weekend"; distinctDates: number; totalRidership: number; meanDailyRidership: number };

export function weekdayVsWeekend(rows: RidershipByDateRow[]): WeekdayWeekendPoint[] {
  const groups = { weekday: { count: 0, total: 0 }, weekend: { count: 0, total: 0 } };
  for (const row of rows) {
    const bucket = row.is_weekend ? groups.weekend : groups.weekday;
    bucket.count += 1;
    bucket.total += row.total_ridership;
  }
  return [
    { dayType: "Weekday", distinctDates: groups.weekday.count, totalRidership: groups.weekday.total, meanDailyRidership: groups.weekday.count ? groups.weekday.total / groups.weekday.count : 0 },
    { dayType: "Weekend", distinctDates: groups.weekend.count, totalRidership: groups.weekend.total, meanDailyRidership: groups.weekend.count ? groups.weekend.total / groups.weekend.count : 0 },
  ];
}

const DAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

export type DayOfWeekPoint = { dayOfWeek: string; distinctDates: number; totalRidership: number; meanDailyRidership: number };

export function byDayOfWeek(rows: RidershipByDateRow[]): DayOfWeekPoint[] {
  const groups = new Map<string, { count: number; total: number }>();
  for (const row of rows) {
    const key = row.day_of_week;
    const existing = groups.get(key) ?? { count: 0, total: 0 };
    existing.count += 1;
    existing.total += row.total_ridership;
    groups.set(key, existing);
  }
  return DAY_ORDER.filter((day) => groups.has(day)).map((day) => {
    const group = groups.get(day)!;
    return { dayOfWeek: day, distinctDates: group.count, totalRidership: group.total, meanDailyRidership: group.total / group.count };
  });
}

export type ConcentrationPoint = { cumulativeRoutePct: number; cumulativeRidershipPct: number };

export type ConcentrationResult = {
  points: ConcentrationPoint[];
  giniCoefficient: number | null;
  top10SharePct: number | null;
};

/**
 * A Lorenz-curve style concentration view of ridership across routes,
 * derived from /ridership/routes. Replaces the record-level scatter plot
 * the architecture doc envisioned, since no scatter-sampling endpoint
 * exists on the backend.
 */
export function routeConcentration(rows: RidershipByRouteRow[]): ConcentrationResult {
  if (rows.length === 0) return { points: [], giniCoefficient: null, top10SharePct: null };

  const sorted = [...rows].sort((a, b) => a.total_ridership - b.total_ridership);
  const total = sorted.reduce((sum, row) => sum + row.total_ridership, 0);
  const n = sorted.length;

  const points: ConcentrationPoint[] = [{ cumulativeRoutePct: 0, cumulativeRidershipPct: 0 }];
  let cumulativeRidership = 0;
  sorted.forEach((row, index) => {
    cumulativeRidership += row.total_ridership;
    points.push({
      cumulativeRoutePct: ((index + 1) / n) * 100,
      cumulativeRidershipPct: total ? (cumulativeRidership / total) * 100 : 0,
    });
  });

  // Gini coefficient via the trapezoidal-rule area under the Lorenz curve.
  let areaUnderCurve = 0;
  for (let i = 1; i < points.length; i += 1) {
    const dx = (points[i].cumulativeRoutePct - points[i - 1].cumulativeRoutePct) / 100;
    const avgY = (points[i].cumulativeRidershipPct + points[i - 1].cumulativeRidershipPct) / 2 / 100;
    areaUnderCurve += dx * avgY;
  }
  const giniCoefficient = total ? 1 - 2 * areaUnderCurve : null;

  const top10Count = Math.max(1, Math.round(n * 0.1));
  const top10Share = sorted.slice(n - top10Count).reduce((sum, row) => sum + row.total_ridership, 0);
  const top10SharePct = total ? (top10Share / total) * 100 : null;

  return { points, giniCoefficient, top10SharePct };
}

export type CorrelationBar = { id: string; label: string; pearsonR: number | null; spearmanRho: number | null; strength: string; n: number };

/** Flattens the record-level and route-level correlation maps from /relationships/summary into a single chart dataset. */
export function correlationDataset(recordLevel: Record<string, CorrelationPair>, routeLevel: Record<string, CorrelationPair>): CorrelationBar[] {
  const toBars = (source: Record<string, CorrelationPair>, level: string) =>
    Object.entries(source).map(([key, pair]) => ({
      id: `${level}:${key}`,
      label: key.replace(/_/g, " "),
      pearsonR: pair.pearson_r,
      spearmanRho: pair.spearman_rho,
      strength: pair.strength,
      n: pair.n,
    }));
  return [...toBars(recordLevel, "record"), ...toBars(routeLevel, "route")];
}
