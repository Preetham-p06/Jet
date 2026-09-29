/** Dashboard-only formatters layered on `lib/format.ts`. */
import { formatCents } from "@/lib/format";

export { formatCents, formatDuration } from "@/lib/format";

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
 * A leg's local departure. The API sends `depart_local` as a wall-clock time
 * in `depart_tz`, so format it in that zone (falling back to the string).
 */
export function fmtLocal(iso: string | null | undefined, tz?: string | null, withWeekday = false): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (!valid(d)) return iso;
  const opts: Intl.DateTimeFormatOptions = {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    ...(withWeekday ? { weekday: "short" } : {}),
  };
  try {
    return new Intl.DateTimeFormat("en-US", { ...opts, timeZone: tz ?? undefined }).format(d);
  } catch {
    return new Intl.DateTimeFormat("en-US", opts).format(d);
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
export function humanize(v: string | null | undefined): string {
  if (!v) return "—";
  const s = v.replace(/[_-]+/g, " ").trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export const CATEGORY_LABEL: Record<string, string> = {
  turboprop: "Turboprop",
  very_light: "Very light jet",
  light: "Light jet",
  midsize: "Midsize",
  super_midsize: "Super-midsize",
  heavy: "Heavy",
  ultra_long_range: "Ultra long range",
  airliner: "Airliner",
};

export function categoryLabel(c: string | null | undefined): string {
  if (!c) return "—";
  return CATEGORY_LABEL[c] ?? humanize(c);
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
