"use client";

import { motion } from "motion/react";
import { StatusDot } from "@/components/ui/status-dot";
import { LOG_LINES } from "@/lib/demo-data";
import { EASE_OUT_EXPO } from "@/lib/animations";
import { cn } from "@/lib/utils";

export function ProcessingLog({ step, className }: { step: number; className?: string }) {
  const lines = LOG_LINES.filter((l) => l.at <= step);
  const done = step >= 9;

  return (
    <div className={cn("flex flex-col font-mono text-[10.5px] leading-5", className)} aria-hidden="true">
      <div className="mb-3 flex items-center justify-between">
        <span className="eyebrow text-[10px] text-fg-dim">JetStream intelligence</span>
        <span className="inline-flex items-center gap-1.5 text-[10px] text-fg-dim">
          <StatusDot tone={done ? "green" : "cyan"} pulse={!done} />
          {done ? "IDLE" : "LIVE"}
        </span>
      </div>
      <ul className="flex flex-col gap-0.5">
        {lines.map((l, i) => (
          <motion.li
            key={`${l.t}-${l.text}`}
            initial={{ opacity: 0, x: -6 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.35, ease: EASE_OUT_EXPO, delay: i === lines.length - 1 ? 0 : 0 }}
            className="flex gap-2.5"
          >
            <span className="shrink-0 text-fg-dim">{l.t}</span>
            <span
              className={cn(
                "truncate text-fg-muted",
                l.tone === "warn" && "text-amber",
                l.tone === "ok" && "text-green",
              )}
            >
              {l.text}
            </span>
          </motion.li>
        ))}
        {!done && (
          <li className="flex gap-2.5">
            <span className="shrink-0 text-fg-dim">--:--:--</span>
            <span className="inline-block h-3.5 w-1.5 translate-y-[3px] animate-pulse bg-cyan/70 motion-reduce:animate-none" />
          </li>
        )}
      </ul>
    </div>
  );
}
