import "server-only";

import { cache } from "react";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { ApiError, SESSION_COOKIE } from "@/lib/api/errors";
import { serverApi } from "@/lib/api/server";
import type { Me } from "@/lib/api/types";

/**
 * The real auth check (proxy.ts is only optimistic). Memoized per request with
 * React `cache`, so layouts and pages can all call it for one `/auth/me` hit.
 */
export const verifySession = cache(async (): Promise<Me> => {
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  if (!token) redirect("/login");

  let me: Me | null = null;
  try {
    me = await serverApi<Me>("/auth/me", { token });
  } catch (e) {
    // Backend down or 5xx: surface the error instead of bouncing to /login.
    if (!(e instanceof ApiError) || (e.status !== 401 && e.status !== 403)) throw e;
  }
  // `redirect` throws, so it stays outside the try block.
  if (!me) redirect("/login");
  return me;
});
