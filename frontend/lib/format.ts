import { formatUSD } from "@/lib/utils";

/** Integer USD cents → "$12,345" (whole dollars, like the landing page). */
export function formatCents(cents: number | null | undefined, fallback = "—"): string {
  if (cents == null || !Number.isFinite(cents)) return fallback;
  return formatUSD(Math.round(cents) / 100);
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
