import { formatUSD } from "@/lib/utils";

/** Integer USD cents (`*_cents` fields are always USD) → "$12,345" (whole dollars, like the landing page). */
export function formatCents(cents: number | null | undefined, fallback = "—"): string {
  if (cents == null || !Number.isFinite(cents)) return fallback;
  return formatUSD(Math.round(cents) / 100);
}

/**
 * ISO 4217 minor-unit exponents that differ from 2. Mirrors
 * `backend/app/services/money.py` (`_MINOR_EXPONENTS`); keep the two in sync.
 */
const MINOR_EXPONENTS: Readonly<Record<string, number>> = { JPY: 0, KRW: 0, CLP: 0, BHD: 3, KWD: 3 };

/** Digits after the decimal point for `currency` (JPY → 0, KWD → 3, else 2). */
export function minorExponent(currency: string | null | undefined): number {
  return MINOR_EXPONENTS[(currency ?? "USD").toUpperCase()] ?? 2;
}

/** Integer minor units → major units (`1234, "JPY"` → 1234; `1234, "USD"` → 12.34). */
export function minorToMajor(minor: number, currency: string | null | undefined): number {
  return minor / 10 ** minorExponent(currency);
}

/** Major units → integer minor units, rounded half away from zero. */
export function majorToMinor(major: number, currency: string | null | undefined): number {
  const scaled = major * 10 ** minorExponent(currency);
  // toPrecision strips binary noise such as 1.005 * 100 = 100.49999999999999.
  const clean = Number(scaled.toPrecision(15));
  return Math.sign(clean) * Math.round(Math.abs(clean));
}

/**
 * Integer minor units in `currency` → "¥1,234" / "KWD 1.250" / "€12.50".
 * Shows the currency's full precision; for USD use `formatCents` for whole dollars.
 */
export function formatMinor(
  minor: number | null | undefined,
  currency: string | null | undefined,
  fallback = "—",
): string {
  if (minor == null || !Number.isFinite(minor)) return fallback;
  const code = (currency ?? "USD").toUpperCase();
  const digits = minorExponent(code);
  const major = minorToMajor(minor, code);
  try {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: code,
      minimumFractionDigits: major % 1 === 0 ? 0 : digits,
      maximumFractionDigits: digits,
    }).format(major);
  } catch {
    // Unknown code (RangeError): fall back to "1,234.50 XYZ".
    return `${major.toLocaleString("en-US", { maximumFractionDigits: digits })} ${code}`;
  }
}

/** Minutes → "2h 58m" / "45m" / "3h". */
export function formatDuration(minutes: number | null | undefined, fallback = "—"): string {
  if (minutes == null || !Number.isFinite(minutes) || minutes < 0) return fallback;
  const total = Math.round(minutes);
  const h = Math.floor(total / 60);
  const m = total % 60;
  if (h === 0) return `${m}m`;
  if (m === 0) return `${h}h`;
  return `${h}h ${m}m`;
}

export type ConfidenceTier = "high" | "neutral" | "review";

/** Confidence is 0–100 (API ints). ≥90 high, ≥75 neutral, below that needs review. */
export function confidenceTier(score: number): ConfidenceTier {
  if (score >= 90) return "high";
  if (score >= 75) return "neutral";
  return "review";
}

/** Display label for an aircraft category enum ("super_midsize" → "Super-midsize"). */
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
  const s = c.replace(/[_-]+/g, " ").trim();
  return CATEGORY_LABEL[c] ?? s.charAt(0).toUpperCase() + s.slice(1);
}
