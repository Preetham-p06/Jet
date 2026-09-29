/** Shared by the browser client and the server fetcher. Backend errors are `{detail, code}`. */

export const API_PREFIX = "/api/v1";
export const SESSION_COOKIE = "js_session";
export const CLIENT_HEADER = { "X-JetStream-Client": "web" } as const;

export class ApiError extends Error {
  readonly status: number;
  readonly code: string | null;
  readonly detail: unknown;

  constructor(status: number, code: string | null, detail: unknown) {
    super(messageFromDetail(detail) ?? `Request failed (${status})`);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

/** Flattens a FastAPI `detail`: a string, or a list of `{msg}` validation errors. */
function messageFromDetail(detail: unknown): string | null {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d) => (d && typeof d === "object" && "msg" in d ? String((d as { msg: unknown }).msg) : null))
      .filter(Boolean);
    return msgs.length ? msgs.join("; ") : null;
  }
  return null;
}

/** `/trips` → `/api/v1/trips`; already-prefixed paths pass through. */
export function apiPath(path: string): string {
  if (path.startsWith(API_PREFIX)) return path;
  return `${API_PREFIX}${path.startsWith("/") ? path : `/${path}`}`;
}

export async function parseBody(res: Response): Promise<unknown> {
  if (res.status === 204 || res.status === 205) return undefined;
  const type = res.headers.get("content-type") ?? "";
  if (type.includes("application/json")) {
    try {
      return await res.json();
    } catch {
      return undefined;
    }
  }
  const text = await res.text();
  return text || undefined;
}

export async function toApiError(res: Response): Promise<ApiError> {
  const body = await parseBody(res);
  if (body && typeof body === "object") {
    const { detail, code } = body as { detail?: unknown; code?: unknown };
    return new ApiError(res.status, typeof code === "string" ? code : null, detail ?? body);
  }
  return new ApiError(res.status, null, body ?? res.statusText);
}
