import { cn } from "@/lib/utils";

type Props = {
  tone?: "green" | "cyan" | "amber";
  pulse?: boolean;
  className?: string;
};

const tones = {
  green: "bg-green",
  cyan: "bg-cyan",
  amber: "bg-amber",
};

export function StatusDot({ tone = "green", pulse = true, className }: Props) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "inline-block h-1.5 w-1.5 shrink-0 rounded-full",
        tones[tone],
        pulse && tone === "green" && "animate-pulse-dot motion-reduce:animate-none",
        className,
      )}
    />
  );
}
