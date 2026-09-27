import { AlertTriangle, Check } from "lucide-react";
import { cn } from "@/lib/utils";

type Props = {
  value: number;
  label?: string;
  className?: string;
  size?: "sm" | "md";
  verified?: boolean;
};

const C = 2 * Math.PI * 5;

export function ConfidenceBadge({ value, label, className, size = "sm", verified }: Props) {
  const tone = verified
    ? "text-green border-green/30 bg-green/[0.08]"
    : value >= 90
      ? "text-cyan border-cyan/25 bg-cyan/[0.06]"
      : value >= 75
        ? "text-fg-muted border-line-strong bg-white/[0.03]"
        : "text-amber border-amber/30 bg-amber/[0.08]";

  return (
    <span
      className={cn(
        "tabular inline-flex items-center gap-1.5 rounded-full border font-mono",
        size === "sm" ? "px-2 py-0.5 text-[11px]" : "px-2.5 py-1 text-xs",
        tone,
        className,
      )}
      aria-label={`${label ?? "Confidence"} ${value} percent${verified ? ", verified" : ""}`}
    >
      {verified ? (
        <Check className="h-3 w-3" strokeWidth={2.5} aria-hidden="true" />
      ) : value < 75 ? (
        <AlertTriangle className="h-3 w-3" strokeWidth={2.25} aria-hidden="true" />
      ) : (
        <svg viewBox="0 0 12 12" className="h-3 w-3 -rotate-90" aria-hidden="true">
          <circle cx="6" cy="6" r="5" fill="none" stroke="currentColor" strokeOpacity="0.2" strokeWidth="1.5" />
          <circle
            cx="6"
            cy="6"
            r="5"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeDasharray={`${(C * value) / 100} ${C}`}
          />
        </svg>
      )}
      {label && <span className="text-fg-dim">{label}</span>}
      <span>{value}%</span>
    </span>
  );
}
