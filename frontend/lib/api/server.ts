import "server-only";

import { cookies } from "next/headers";
import { CLIENT_HEADER, SESSION_COOKIE, apiPath, parseBody, toApiError } from "./errors";

export { ApiError } from "./errors";

const BACKEND_URL = (process.env.BACKEND_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

type ServerOptions = {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  json?: unknown;
  signal?: AbortSignal;
  /** Override the bearer token; defaults to the request's `js_session` cookie. */
  token?: string | null;
};

/**
 * Server-side fetch straight to FastAPI (no rewrite hop). The session cookie is
 * forwarded as `Authorization: Bearer`, and responses are never cached.
 */
export async function serverApi<T>(path: string, opts: ServerOptions = {}): Promise<T> {
  const token =
    opts.token !== undefined ? opts.token : ((await cookies()).get(SESSION_COOKIE)?.value ?? null);

  const headers: Record<string, string> = { ...CLIENT_HEADER, Accept: "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  let body: string | undefined;
  if (opts.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.json);
  }

  const res = await fetch(`${BACKEND_URL}${apiPath(path)}`, {
    method: opts.method ?? (body ? "POST" : "GET"),
    headers,
    body,
    signal: opts.signal,
    cache: "no-store",
  });

  if (!res.ok) throw await toApiError(res);
  return (await parseBody(res)) as T;
}
