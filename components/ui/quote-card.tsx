"use client";

import { useState, type FocusEvent, type PointerEvent } from "react";
import { AnimatePresence, motion } from "motion/react";
import { AlertTriangle, ChevronDown, Wifi } from "lucide-react";
import { AnimatedNumber } from "@/components/ui/animated-number";
import { ConfidenceBadge } from "@/components/ui/confidence-badge";
import { Tooltip } from "@/components/ui/tooltip";
import type { Quote } from "@/lib/demo-data";
import { EASE_OUT_EXPO, enter } from "@/lib/animations";
import { cn, formatUSD } from "@/lib/utils";

type Props = {
  quote: Quote;
  /** Card has entered the shell. */
  visible: boolean;
  /** AI extraction in progress (skeleton + shimmer). */
  extracting: boolean;
  /** Structured fields are available. */
  populated: boolean;
  /** Confidence has been re-scored. */
  scored: boolean;
  /** Recommended glow. */
  highlight: boolean;
  /** Missing-charge warning is shown. */
  warned: boolean;
};

function Skeleton({ className }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn("block rounded bg-white/[0.06] animate-pulse motion-reduce:animate-none", className)}
    />
  );
}

export function QuoteCard({ quote, visible, extracting, populated, scored, highlight, warned }: Props) {
  const [open, setOpen] = useState(false);
  const addedCharges = quote.fees.filter((f) => f.amount !== null);
  const missing = quote.fees.filter((f) => f.flagged);

  const onEnter = (e: PointerEvent<HTMLElement>) => {
    if (e.pointerType !== "touch") setOpen(true);
  };
  const onLeave = (e: PointerEvent<HTMLElement>) => {
    if (e.pointerType !== "touch") setOpen(false);
  };
  const onBlur = (e: FocusEvent<HTMLElement>) => {
    if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setOpen(false);
  };

  return (
    <motion.article
      initial={{ opacity: 0, y: 16, scale: 0.97 }}
      animate={visible ? { opacity: 1, y: 0, scale: 1 } : { opacity: 0, y: 16, scale: 0.97 }}
      transition={enter}
      onPointerEnter={onEnter}
      onPointerLeave={onLeave}
      onFocus={() => setOpen(true)}
      onBlur={onBlur}
      aria-label={`${quote.operator} · ${quote.aircraft}`}
      className={cn(
        "group relative flex flex-col rounded-xl border p-3.5",
        "bg-[linear-gradient(180deg,rgba(255,255,255,0.045),rgba(255,255,255,0.015))]",
        "transition-[transform,border-color,box-shadow,background-color] duration-300 ease-out-expo",
        open && "-translate-y-1 border-white/[0.18] shadow-card",
        highlight
          ? "border-cyan/40 shadow-[0_0_0_1px_rgba(89,217,255,0.25),0_24px_60px_-24px_rgba(89,217,255,0.45)]"
          : warned
            ? "border-amber/25"
            : "border-line",
      )}
    >
      {/* recommended glow wash */}
      <AnimatePresence>
        {highlight && (
          <motion.span
            aria-hidden="true"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.8 }}
            className="pointer-events-none absolute inset-0 rounded-xl bg-[radial-gradient(120%_80%_at_50%_-10%,rgba(89,217,255,0.12),transparent_60%)]"
          />
        )}
      </AnimatePresence>

      {/* status tag, floating on the card's top edge so it never crowds the title */}
      <AnimatePresence>
        {highlight && (
          <motion.span
            key="rec"
            initial={{ opacity: 0, y: 4, scale: 0.92 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.35, ease: EASE_OUT_EXPO }}
            className="absolute -top-2.5 right-3 z-10 rounded-full border border-cyan/35 bg-[#0c1a24] px-2 py-0.5 font-mono text-[9.5px] tracking-[0.12em] text-cyan shadow-[0_0_14px_rgba(89,217,255,0.3)]"
          >
            RECOMMENDED
          </motion.span>
        )}
        {warned && !highlight && (
          <motion.span
            key="warn"
            initial={{ opacity: 0, y: 4, scale: 0.92 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.35, ease: EASE_OUT_EXPO }}
            className="absolute -top-2.5 right-3 z-10 inline-flex items-center gap-1 rounded-full border border-amber/35 bg-[#1c1710] px-2 py-0.5 font-mono text-[9.5px] tracking-[0.12em] text-amber"
          >
            <AlertTriangle className="h-2.5 w-2.5" aria-hidden="true" />
            FLAGGED
          </motion.span>
        )}
      </AnimatePresence>

      <header className="relative min-w-0">
        <p className="truncate text-[11px] text-fg-dim">{quote.operator}</p>
        <p className="mt-0.5 truncate text-[13.5px] font-medium leading-tight text-fg">{quote.aircraft}</p>
        <p className="mt-0.5 flex items-center gap-1.5 text-[11px] text-fg-muted">
          {quote.category} · {quote.seats} seats
          {quote.wifi && <Wifi className="h-3 w-3 text-fg-dim" aria-label="Wi-Fi" />}
        </p>
      </header>

      <div className="relative mt-3.5 flex items-end justify-between gap-2">
        <div>
          <p className="whitespace-nowrap font-mono text-[9.5px] uppercase tracking-[0.14em] text-fg-dim">
            {extracting ? <span className="shimmer-text">Extracting…</span> : "Headline quote"}
          </p>
          {populated ? (
            <p className="mt-0.5 text-[21px] font-semibold leading-none tracking-[-0.02em] text-fg">
              <AnimatedNumber value={quote.headline} from={0} start="immediate" duration={0.9} />
            </p>
          ) : (
            <Skeleton className="mt-1.5 h-5 w-[92px]" />
          )}
        </div>
        {populated ? (
          <ConfidenceBadge value={scored ? quote.finalFit : quote.fit} label="fit" />
        ) : (
          <Skeleton className="h-5 w-[58px] rounded-full" />
        )}
      </div>

      {/* fixed-height detail zone: summary ⇄ breakdown crossfade, no layout shift */}
      <div className="relative mt-3.5 h-[126px] border-t border-line">
        <AnimatePresence initial={false}>
          {populated && !open && (
            <motion.div
              key="summary"
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.22, ease: EASE_OUT_EXPO }}
              className="absolute inset-x-0 top-3"
            >
              <p className="font-mono text-[9.5px] uppercase tracking-[0.14em] text-fg-dim">True cost</p>
              <p className="tabular mt-0.5 text-lg font-semibold tracking-[-0.02em] text-fg">
                {formatUSD(quote.trueCost)}
              </p>
              <p className="mt-2 text-[11px] leading-snug text-fg-muted">
                {addedCharges.length} added charge{addedCharges.length === 1 ? "" : "s"} detected
              </p>
              {missing.length > 0 && warned && (
                <p className="mt-1 inline-flex items-center gap-1 text-[11px] text-amber">
                  <AlertTriangle className="h-3 w-3" aria-hidden="true" />
                  {quote.warning}
                </p>
              )}
            </motion.div>
          )}

          {populated && open && (
            <motion.dl
              key="breakdown"
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.22, ease: EASE_OUT_EXPO }}
              className="absolute inset-x-0 top-2.5 text-[11px]"
            >
              {quote.fees.map((f) => (
                <div key={f.label} className="flex items-center justify-between py-[3px]">
                  <dt className="text-fg-muted">{f.label}</dt>
                  <dd className={cn("tabular font-mono", f.flagged ? "text-amber" : "text-fg")}>
                    {f.amount === null ? (f.flagged ? "Not stated" : "Included") : formatUSD(f.amount)}
                  </dd>
                </div>
              ))}
              <div className="mt-1.5 flex items-center justify-between border-t border-line pt-1.5">
                <dt>
                  <Tooltip
                    triggerClassName="text-fg"
                    content={
                      missing.length > 0
                        ? `JetStream detected ${addedCharges.length} additional cost components and ${missing.length} charge that the operator did not state.`
                        : `JetStream detected ${addedCharges.length} additional cost components that were not included in the headline quote.`
                    }
                  >
                    True cost
                  </Tooltip>
                </dt>
                <dd className="tabular font-mono text-[12.5px] font-semibold text-fg">
                  {formatUSD(quote.trueCost)}
                  {missing.length > 0 && <span className="text-amber">+</span>}
                </dd>
              </div>
            </motion.dl>
          )}

          {!populated && (
            <motion.div key="skeleton" exit={{ opacity: 0 }} className="absolute inset-x-0 top-3 space-y-2">
              <Skeleton className="h-3 w-16" />
              <Skeleton className="h-5 w-24" />
              <Skeleton className="h-3 w-28" />
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        disabled={!populated}
        className="relative -mx-1 -mb-1 mt-1 inline-flex h-8 items-center gap-1 self-start rounded-md px-1 font-mono text-[10px] uppercase tracking-[0.12em] text-fg-dim transition-colors hover:text-fg disabled:opacity-0"
      >
        {open ? "Hide" : "Details"}
        <ChevronDown
          className={cn("h-3 w-3 transition-transform duration-200", open && "rotate-180")}
          aria-hidden="true"
        />
      </button>
    </motion.article>
  );
}
