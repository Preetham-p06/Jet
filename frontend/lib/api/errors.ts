/**
 * Shared by the browser client and the server fetcher. Backend errors are
 * `{detail, code, fields?}`; `fields` maps a dotted location (`body.legs.0.origin`)
 * to a message on 422s and on some domain errors.
 */

export const API_PREFIX = "/api/v1";
export const SESSION_COOKIE = "js_session";
export const CLIENT_HEADER = { "X-JetStream-Client": "web" } as const;

export type FieldErrors = Readonly<Record<string, string>>;

export class ApiError extends Error {
  readonly status: number;
  readonly code: string | null;
  readonly detail: unknown;
  /** Per-field messages keyed by dotted location, without the `body.`/`query.`/`path.` prefix. */
  readonly fields: FieldErrors;

  constructor(status: number, code: string | null, detail: unknown, fields: FieldErrors = {}) {
    super(messageFromDetail(detail) ?? `Request failed (${status})`);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.detail = detail;
    this.fields = fields;
  }

  /**
   * The message for `name` (e.g. `"email"` or `"legs.0.origin"`), matching the
   * key itself or any nested key under it. Null when the field has no error.
   */
  fieldError(name: string): string | null {
    if (!name) return null;
    if (this.fields[name]) return this.fields[name];
    const prefix = `${name}.`;
    for (const [k, v] of Object.entries(this.fields)) if (k.startsWith(prefix)) return v;
    return null;
  }

  get hasFieldErrors(): boolean {
    return Object.keys(this.fields).length > 0;
  }
}

/** The API's message for form field `name` on `error`, if it is an `ApiError` that has one. */
export function fieldErrorOf(error: unknown, name: string): string | null {
  return error instanceof ApiError ? error.fieldError(name) : null;
}

/** "legs.0.origin_icao" → "Legs 1 origin icao". */
export function fieldLabel(key: string): string {
  const s = key
    .split(".")
    .map((p) => (/^\d+$/.test(p) ? String(Number(p) + 1) : p.replace(/_/g, " ")))
    .join(" ")
    .trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function messageFromDetail(detail: unknown): string | null {
  return typeof detail === "string" ? detail : null;
}

const LOCATION_PREFIX = /^(body|query|path|header|cookie|form)\./;
const LOCATION_BARE = /^(body|query|path|header|cookie|form)?$/;

/** A `fields` value as text: a string, or a list of strings / `{message}` objects. */
function fieldText(v: unknown): string | null {
  if (typeof v === "string") return v;
  if (Array.isArray(v)) {
    const parts = v
      .map((x) =>
        typeof x === "string"
          ? x
          : x && typeof x === "object" && typeof (x as { message?: unknown }).message === "string"
            ? (x as { message: string }).message
            : null,
      )
      .filter((x): x is string => !!x);
    return parts.length ? parts.join("; ") : null;
  }
  return null;
}

/** `{"body.email": "…"}` → `{"email": "…"}`; drops values that have no text. */
function normalizeFields(raw: unknown): FieldErrors {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return {};
  const out: Record<string, string> = {};
  for (const [k, rawValue] of Object.entries(raw as Record<string, unknown>)) {
    const v = fieldText(rawValue);
    if (v == null) continue;
    // A bare location ("body") is a whole-request error; key it as "".
    const key = LOCATION_BARE.test(k) ? "" : k.replace(LOCATION_PREFIX, "");
    out[key] ??= v;
  }
  return out;
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
    const { detail, code, fields } = body as { detail?: unknown; code?: unknown; fields?: unknown };
    return new ApiError(res.status, typeof code === "string" ? code : null, detail ?? body, normalizeFields(fields));
  }
  return new ApiError(res.status, null, body ?? res.statusText);
}
