"use client";

import { useEffect, useRef } from "react";
import { animate, useInView, useMotionValue } from "motion/react";
import { EASE_OUT_EXPO } from "@/lib/animations";
import { useReducedMotionSafe } from "@/lib/use-reduced-motion";
import { cn, formatUSD } from "@/lib/utils";

type Props = {
  value: number;
  /** Starting value for the first animation. Defaults to `value` (no count-up). */
  from?: number;
  format?: (n: number) => string;
  duration?: number;
  delay?: number;
  /** Start when scrolled into view (default) or immediately on mount / value change. */
  start?: "inView" | "immediate";
  className?: string;
};

/**
 * Animates between numeric values, writing to the DOM directly so the
 * page does not re-render sixty times a second.
 */
export function AnimatedNumber({
  value,
  from,
  format = formatUSD,
  duration = 1.1,
  delay = 0,
  start = "inView",
  className,
}: Props) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.5 });
  const reduce = useReducedMotionSafe();
  const mv = useMotionValue(from ?? value);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (start === "inView" && !inView) return;

    if (reduce) {
      mv.set(value);
      el.textContent = format(value);
      return;
    }

    const controls = animate(mv, value, {
      duration,
      delay,
      ease: EASE_OUT_EXPO,
      onUpdate: (v) => {
        el.textContent = format(Math.round(v));
      },
    });
    return () => controls.stop();
  }, [value, inView, reduce, start, duration, delay, format, mv]);

  return (
    <span ref={ref} className={cn("tabular", className)}>
      {format(from ?? value)}
    </span>
  );
}
