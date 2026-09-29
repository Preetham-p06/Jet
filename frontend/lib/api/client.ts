import { ApiError, CLIENT_HEADER, apiPath, parseBody, toApiError } from "./errors";

export { ApiError } from "./errors";

type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export type ApiOptions = {
  method?: Method;
  /** JSON body; sets `Content-Type: application/json`. */
  json?: unknown;
  /** Multipart body; the browser sets the boundary. */
  form?: FormData;
  signal?: AbortSignal;
  /**
   * On a 401 in the browser, send the user to `/login?next=…` (default true).
   * Login, signup and public pages pass false so they can show the error.
   */
  redirectOn401?: boolean;
};

/**
 * Browser-side fetch to the backend through the `/api/*` rewrite.
 * Same-origin, so the httpOnly `js_session` cookie rides along.
 */
export async function api<T>(path: string, opts: ApiOptions = {}): Promise<T> {
  const { json, form, signal, redirectOn401 = true } = opts;
  const method = opts.method ?? (json !== undefined || form ? "POST" : "GET");

  const headers: Record<string, string> = { ...CLIENT_HEADER, Accept: "application/json" };
  let body: BodyInit | undefined;
  if (form) {
    body = form;
  } else if (json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(json);
  }

  const res = await fetch(apiPath(path), {
    method,
    headers,
    body,
    signal,
    credentials: "same-origin",
    cache: "no-store",
  });

  if (!res.ok) {
    const err = await toApiError(res);
    if (res.status === 401 && redirectOn401) redirectToLogin();
    throw err;
  }
  return (await parseBody(res)) as T;
}

function redirectToLogin() {
  if (typeof window === "undefined") return;
  const { pathname, search } = window.location;
  if (pathname === "/login" || pathname === "/signup") return;
  // A hard navigation on purpose: this runs outside React (no router) and
  // drops any client state tied to the expired session.
  // eslint-disable-next-line @next/next/no-location-assign-relative-destination
  window.location.assign(`/login?next=${encodeURIComponent(pathname + search)}`);
}

export function isApiError(e: unknown): e is ApiError {
  return e instanceof ApiError;
}
