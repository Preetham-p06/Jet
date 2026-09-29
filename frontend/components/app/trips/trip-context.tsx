"use client";

import { createContext, useContext } from "react";
import type { Trip } from "@/lib/api/endpoints";

export type TripCtx = {
  tripId: string;
  trip: Trip | undefined;
  /** Bumped after any mutation that can change quotes, flags or the recommendation. */
  version: number;
  /** Re-fetch the trip header and every tab keyed on `version`. */
  bump: () => void;
  goTab: (tab: TripTab) => void;
};

export const TRIP_TABS = ["overview", "quotes", "review", "flags", "recommendation", "proposals", "activity"] as const;
export type TripTab = (typeof TRIP_TABS)[number];

export function isTripTab(v: unknown): v is TripTab {
  return typeof v === "string" && (TRIP_TABS as readonly string[]).includes(v);
}

export const TripContext = createContext<TripCtx | null>(null);

export function useTrip(): TripCtx {
  const ctx = useContext(TripContext);
  if (!ctx) throw new Error("useTrip() must be used inside <TripWorkspace>");
  return ctx;
}
