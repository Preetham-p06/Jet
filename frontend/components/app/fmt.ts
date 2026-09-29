/** Dashboard-only formatters layered on `lib/format.ts`. */
import { formatCents } from "@/lib/format";

export { CATEGORY_LABEL, categoryLabel, formatCents, formatDuration } from "@/lib/format";

const dtf = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
const df = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" });
const dfw = new Intl.DateTimeFormat("en-US", { weekday: "short", month: "short", day: "numeric", year: "numeric" });

function valid(d: Date) {
  return !Number.isNaN(d.getTime());
}

export function fmtDateTime(iso: string | null | undefined, fallback = "—"): string {
  if (!iso) return fallback;
  const d = new Date(iso);
  return valid(d) ? dtf.format(d) : fallback;
}

export function fmtDate(iso: string | null | undefined, fallback = "—"): string {
  if (!iso) return fallback;
  const d = new Date(iso);
  return valid(d) ? df.format(d) : fallback;
}

/**
 * A leg's local departure. `depart_local` is a wall-clock time at the origin
 * (no offset), so it is formatted as-is, never shifted into the viewer's zone.
 * If the API ever sends an offset, it is formatted in `tz` instead.
 */
export function fmtLocal(iso: string | null | undefined, tz?: string | null, withWeekday = false): string {
  if (!iso) return "—";
  const hasOffset = /(Z|[+-]\d{2}:?\d{2})$/.test(iso);
  const d = new Date(hasOffset ? iso : `${iso}Z`);
  if (!valid(d)) return iso;
  const opts: Intl.DateTimeFormatOptions = {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    ...(withWeekday ? { weekday: "short" } : {}),
  };
  try {
    return new Intl.DateTimeFormat("en-US", { ...opts, timeZone: hasOffset ? (tz ?? undefined) : "UTC" }).format(d);
  } catch {
    return new Intl.DateTimeFormat("en-US", { ...opts, timeZone: "UTC" }).format(d);
  }
}

export function fmtDateLong(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso.length === 10 ? `${iso}T12:00:00` : iso);
  return valid(d) ? dfw.format(d) : iso;
}

export function fmtRelative(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (!valid(d)) return "—";
  const s = Math.round((Date.now() - d.getTime()) / 1000);
  if (s < 45) return "just now";
  const m = Math.round(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 36) return `${h}h ago`;
  return fmtDate(iso);
}

export function fmtHours(h: number | null | undefined): string {
  if (h == null || !Number.isFinite(h)) return "—";
  return `${h.toFixed(1)} h`;
}

export function fmtMinutesAsHours(min: number | null | undefined): string {
  if (min == null) return "—";
  return fmtHours(min / 60);
}

export function fmtPct(n: number | null | undefined, digits = 0): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return `${n.toFixed(digits)}%`;
}

/** Enum value → "Super midsize". */
const SPECIAL: Record<string, string> = {
  pdf_upload: "PDF upload",
  pdf: "PDF",
  sms: "SMS",
  fet: "FET",
  whatsapp: "WhatsApp",
  fx_converted: "FX converted",
};

export function humanize(v: string | null | undefined): string {
  if (!v) return "—";
  if (SPECIAL[v]) return SPECIAL[v];
  const s = v.replace(/[_-]+/g, " ").trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** "$41,980" with an optional trailing "+" when not fully priced. */
export function trueCostText(known: number | null | undefined, fullyPriced: boolean): string {
  return `${formatCents(known)}${fullyPriced || known == null ? "" : "+"}`;
}

/** `2026-10-18T09:00` for `<input type="datetime-local">` from a Date. */
export function toLocalInput(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** Parse "$1,234.50" / "1234.5" / "41.8k" → cents; null if unparseable. */
export function parseMoneyToCents(input: string): number | null {
  const s = input.trim().toLowerCase().replace(/[$,\s]/g, "").replace(/usd/g, "");
  if (!s) return null;
  const k = s.endsWith("k");
  const n = Number(k ? s.slice(0, -1) : s);
  if (!Number.isFinite(n) || n < 0) return null;
  return Math.round(n * (k ? 1000 : 1) * 100);
}
