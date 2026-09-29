"use client";

import { createContext, useContext } from "react";
import type { Trip } from "@/lib/api/endpoints";
import type { TripTab } from "./trip-tabs";

export type { TripTab } from "./trip-tabs";

export type TripCtx = {
  tripId: string;
  trip: Trip | undefined;
  /** Bumped after any mutation that can change quotes, flags or the recommendation. */
  version: number;
  /** Re-fetch the trip header and every tab keyed on `version`. */
  bump: () => void;
  goTab: (tab: TripTab) => void;
};

export const TripContext = createContext<TripCtx | null>(null);

export function useTrip(): TripCtx {
  const ctx = useContext(TripContext);
  if (!ctx) throw new Error("useTrip() must be used inside <TripWorkspace>");
  return ctx;
}
