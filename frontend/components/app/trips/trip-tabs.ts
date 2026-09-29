/** Plain module (no "use client") so the server page can validate `?tab=`. */
export const TRIP_TABS = ["overview", "quotes", "review", "flags", "recommendation", "proposals", "activity"] as const;
export type TripTab = (typeof TRIP_TABS)[number];

export function isTripTab(v: unknown): v is TripTab {
  return typeof v === "string" && (TRIP_TABS as readonly string[]).includes(v);
}
