"use client";

import { createContext, useContext, type ReactNode } from "react";
import type { Capability, Me } from "@/lib/api/types";

const MeContext = createContext<Me | null>(null);

/** Holds the `/auth/me` payload fetched by the `(app)` server layout. */
export function MeProvider({ me, children }: { me: Me; children: ReactNode }) {
  return <MeContext.Provider value={me}>{children}</MeContext.Provider>;
}

export function useMe(): Me {
  const me = useContext(MeContext);
  if (!me) throw new Error("useMe() must be used inside <MeProvider>");
  return me;
}

/** `const canReview = useCan("field.review")` */
export function useCan(capability: Capability): boolean {
  return useMe().capabilities.includes(capability);
}
