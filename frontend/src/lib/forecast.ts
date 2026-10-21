import type { Heatmap, Plan } from '../api/types';

export const FORECAST_HOURS = 48;

/** Unix ms of forecast hour 0: the first whole hour at or after departure (same rule as the backend). */
export function forecastStartMs(plan: Plan, heatmap?: Heatmap): number {
  if (heatmap) return Date.parse(heatmap.start_time);
  const dep = Date.parse(plan.request.departure_time);
  const hour = 3_600_000;
  return Math.ceil(dep / hour) * hour;
}

/** Seconds after departure that slider position `hour` represents. */
export function secondsAfterDeparture(plan: Plan, hour: number, heatmap?: Heatmap): number {
  return (forecastStartMs(plan, heatmap) + hour * 3_600_000 - Date.parse(plan.request.departure_time)) / 1000;
}
