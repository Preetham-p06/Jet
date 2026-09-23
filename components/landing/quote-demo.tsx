"use client";

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useInView, useMotionValueEvent, useSpring } from "motion/react";
import { useReducedMotionSafe } from "@/lib/use-reduced-motion";
import { AlertTriangle, ArrowRight, Check, RotateCcw } from "lucide-react";
import { LogoMark } from "@/components/ui/logo";
import { QuoteCard } from "@/components/ui/quote-card";
import { AnimatedNumber } from "@/components/ui/animated-number";
import { ConfidenceBadge } from "@/components/ui/confidence-badge";
import { GlowButton } from "@/components/ui/glow-button";
import { StatusDot } from "@/components/ui/status-dot";
import { ProcessingLog } from "@/components/landing/processing-log";
import { QUOTES, RECOMMENDED, REQUEST } from "@/lib/demo-data";
import { EASE_OUT_EXPO, springTilt } from "@/lib/animations";
import { usePointer } from "@/lib/pointer";
import { cn, formatUSD } from "@/lib/utils";

/**
 * Demo steps
 * 1–4  quote cards arrive one by one
 * 5    AI extracting
 * 6    structured fields populate
 * 7    hidden-fee warning
 * 8    total recalculates + confidence updates
 * 9    recommendation + proposal ready
 */
const TIMELINE = [150, 450, 750, 1050, 1500, 2500, 3300, 4000, 4800];
const FINAL_STEP = 9;

const STATUS: Record<number, { text: string; tone: "cyan" | "green" | "amber" }> = {
  0: { text: "Waiting for operator replies", tone: "cyan" },
  1: { text: "Ingesting operator replies", tone: "cyan" },
  5: { text: "Extracting fields", tone: "cyan" },
  6: { text: "Normalizing totals", tone: "cyan" },
  7: { text: "Missing charge flagged", tone: "amber" },
  8: { text: "Scoring confidence", tone: "cyan" },
  9: { text: "4 quotes normalized", tone: "green" },
};

function statusFor(step: number) {
  let key = 0;
  for (const k of Object.keys(STATUS).map(Number)) if (step >= k) key = k;
  return STATUS[key];
}

export function QuoteDemo() {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.2 });
  const reduce = useReducedMotionSafe();
  const [rawStep, setRawStep] = useState(0);
  const [run, setRun] = useState(0);
  /** Under reduced motion the demo shows its finished state immediately. */
  const step = reduce ? FINAL_STEP : rawStep;

  useEffect(() => {
    if (!inView || reduce) return;
    const timers = TIMELINE.map((ms, i) => setTimeout(() => setRawStep(i + 1), ms));
    return () => timers.forEach(clearTimeout);
  }, [inView, reduce, run]);

  const replay = () => {
    setRawStep(0);
    setRun((r) => r + 1);
  };

  /* ---- subtle 3D: shell tilts toward the pointer ---- */
  const { x, y } = usePointer();
  const rx = useSpring(0, springTilt);
  const ry = useSpring(0, springTilt);
  const [tiltOn, setTiltOn] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(hover: hover) and (pointer: fine)");
    const update = () => setTiltOn(mq.matches && !reduce);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, [reduce]);

  useMotionValueEvent(x, "change", (px) => {
    if (!tiltOn || !ref.current) return;
    const r = ref.current.getBoundingClientRect();
    const py = y.get();
    const inside =
      px > r.left - r.width * 0.25 &&
      px < r.right + r.width * 0.25 &&
      py > r.top - r.height * 0.25 &&
      py < r.bottom + r.height * 0.25;
    if (!inside) {
      rx.set(0);
      ry.set(0);
      return;
    }
    const nx = (px - (r.left + r.width / 2)) / (r.width / 2);
    const ny = (py - (r.top + r.height / 2)) / (r.height / 2);
    ry.set(Math.max(-1, Math.min(1, nx)) * 2.4);
    rx.set(Math.max(-1, Math.min(1, ny)) * -2.4);
  });

  const status = statusFor(step);
  const populated = step >= 6;
  const scored = step >= 8;
  const ready = step >= FINAL_STEP;
  const recommendedFees = RECOMMENDED.fees;
  const finalEstimate = scored ? RECOMMENDED.trueCost : RECOMMENDED.headline;

  return (
    <motion.div
      ref={ref}
      style={{ rotateX: rx, rotateY: ry, transformPerspective: 1600 }}
      className="relative will-change-transform"
    >
      {/* under-glow */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -inset-x-6 -bottom-10 top-1/3 -z-10 rounded-[40px] bg-[radial-gradient(60%_60%_at_50%_100%,rgba(91,140,255,0.28),transparent_70%)] blur-3xl"
      />

      <div className="glass-strong edge-light shadow-shell relative overflow-hidden rounded-2xl">
        {/* title bar */}
        <div className="flex h-11 items-center justify-between border-b border-line px-3.5 sm:px-4">
          <div className="flex min-w-0 items-center gap-2.5">
            <LogoMark className="h-4 w-4" />
            <span className="truncate font-mono text-[11px] tracking-[0.14em] text-fg-muted">
              JETSTREAM{" "}
              <span className="hidden sm:inline">
                <span className="text-fg-dim">/</span> QUOTES <span className="text-fg-dim">·</span>
              </span>{" "}
              {REQUEST.id}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <AnimatePresence mode="wait" initial={false}>
              <motion.span
                key={status.text}
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                transition={{ duration: 0.25, ease: EASE_OUT_EXPO }}
                className={cn(
                  "hidden items-center gap-2 rounded-full border px-2.5 py-1 font-mono text-[10.5px] sm:inline-flex",
                  status.tone === "green"
                    ? "border-green/25 bg-green/[0.08] text-green"
                    : status.tone === "amber"
                      ? "border-amber/25 bg-amber/[0.08] text-amber"
                      : "border-line-strong bg-white/[0.03] text-fg-muted",
                )}
                aria-live="polite"
              >
                {status.tone === "green" ? (
                  <Check className="h-3 w-3" strokeWidth={2.5} aria-hidden="true" />
                ) : status.tone === "amber" ? (
                  <AlertTriangle className="h-3 w-3" aria-hidden="true" />
                ) : (
                  <StatusDot tone="cyan" pulse={false} className="animate-pulse motion-reduce:animate-none" />
                )}
                {status.text}
                {!ready && status.tone !== "amber" && <span className="text-fg-dim">…</span>}
              </motion.span>
            </AnimatePresence>
            <span className="whitespace-nowrap rounded-md border border-line px-1.5 py-0.5 font-mono text-[9.5px] tracking-[0.12em] text-fg-dim">
              DEMO DATA
            </span>
            <button
              type="button"
              aria-label="Replay demo"
              onClick={replay}
              className="grid h-8 w-8 place-items-center rounded-md text-fg-dim transition-colors hover:bg-white/[0.06] hover:text-fg"
            >
              <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
          </div>
        </div>

        <div className="grid lg:grid-cols-[1fr_284px]">
          {/* main */}
          <div className="p-3.5 sm:p-5">
            {/* request */}
            <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <p className="eyebrow text-[10px]">Charter request</p>
                <p className="mt-1.5 text-[17px] font-medium tracking-[-0.01em] text-fg sm:text-lg">
                  {REQUEST.from}{" "}
                  <span className="font-mono text-[11px] text-fg-dim">{REQUEST.fromCode}</span>
                  <span className="mx-2 inline-block text-fg-dim" aria-hidden="true">
                    →
                  </span>
                  {REQUEST.to}{" "}
                  <span className="font-mono text-[11px] text-fg-dim">{REQUEST.toCode}</span>
                </p>
                <p className="mt-1 text-[12.5px] text-fg-muted">
                  {REQUEST.date} · {REQUEST.pax} passengers · {REQUEST.depart}
                </p>
              </div>
              <p className="tabular font-mono text-[11px] tracking-[0.14em] text-fg-muted">
                <span className="text-fg">{Math.min(step, 4)}</span> QUOTES FOUND
              </p>
            </div>

            {/* quote cards */}
            <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {QUOTES.map((q, i) => (
                <QuoteCard
                  key={q.id}
                  quote={q}
                  visible={step >= i + 1}
                  extracting={step === 5}
                  populated={populated}
                  scored={scored}
                  highlight={ready && Boolean(q.recommended)}
                  warned={step >= 7 && Boolean(q.warning)}
                />
              ))}
            </div>

            {/* true cost analysis */}
            <div className="mt-4 rounded-xl border border-line bg-black/20 p-3.5 sm:p-4">
              <div className="flex items-center justify-between">
                <p className="eyebrow text-[10px]">
                  True cost analysis <span className="text-fg-dim">·</span>{" "}
                  <span className="normal-case tracking-normal text-fg-muted">{RECOMMENDED.operator}</span>
                </p>
                <AnimatePresence>
                  {step >= 7 && (
                    <motion.p
                      initial={{ opacity: 0, x: 6 }}
                      animate={{ opacity: 1, x: 0 }}
                      exit={{ opacity: 0 }}
                      transition={{ duration: 0.3, ease: EASE_OUT_EXPO }}
                      className="hidden items-center gap-1.5 font-mono text-[10.5px] text-amber sm:inline-flex"
                    >
                      <AlertTriangle className="h-3 w-3" aria-hidden="true" />
                      Summit Executive · fuel surcharge not stated · 61%
                    </motion.p>
                  )}
                </AnimatePresence>
              </div>

              <div className="mt-3 flex min-h-[38px] flex-wrap items-center gap-x-2 gap-y-2 text-[12px]">
                <Chip label="Base quote" value={populated ? formatUSD(RECOMMENDED.headline) : "—"} strong />
                {recommendedFees.map((f, i) => (
                  <AnimatePresence key={f.label}>
                    {step >= 7 && (
                      <motion.div
                        initial={{ opacity: 0, y: 6, scale: 0.96 }}
                        animate={{ opacity: 1, y: 0, scale: 1 }}
                        transition={{ duration: 0.4, ease: EASE_OUT_EXPO, delay: i * 0.12 }}
                        className="flex items-center gap-2"
                      >
                        <span className="font-mono text-fg-dim" aria-hidden="true">
                          +
                        </span>
                        <Chip
                          label={f.label}
                          value={f.amount === null ? "Included" : formatUSD(f.amount)}
                          muted={f.amount === null}
                        />
                      </motion.div>
                    )}
                  </AnimatePresence>
                ))}
              </div>
            </div>

            {/* final estimate */}
            <div className="mt-4 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex items-center gap-5">
                <div>
                  <p className="eyebrow text-[10px]">Final estimate</p>
                  <p className="mt-1 text-[26px] font-semibold leading-none tracking-[-0.03em] text-fg sm:text-[30px]">
                    {populated ? (
                      <AnimatedNumber value={finalEstimate} from={RECOMMENDED.headline} start="immediate" duration={1.2} />
                    ) : (
                      <span className="text-fg-dim">—</span>
                    )}
                  </p>
                </div>
                <div className="border-l border-line pl-5">
                  <p className="eyebrow text-[10px]">Confidence</p>
                  <div className="mt-1.5">
                    {populated ? (
                      <ConfidenceBadge value={scored ? RECOMMENDED.finalFit : RECOMMENDED.fit} size="md" />
                    ) : (
                      <span className="font-mono text-[12px] text-fg-dim">pending</span>
                    )}
                  </div>
                </div>
              </div>
              <div
                className={cn(
                  "transition-[opacity,filter] duration-500 ease-out-expo",
                  ready ? "opacity-100" : "opacity-40 grayscale",
                )}
              >
                <GlowButton size="md" disabled={!ready} icon={<ArrowRight className="h-4 w-4" />}>
                  Generate proposal
                </GlowButton>
              </div>
            </div>
          </div>

          {/* processing log */}
          <aside className="hidden border-l border-line bg-black/25 p-4 lg:block">
            <ProcessingLog step={step} />
          </aside>
        </div>
      </div>
    </motion.div>
  );
}

function Chip({
  label,
  value,
  strong,
  muted,
}: {
  label: string;
  value: string;
  strong?: boolean;
  muted?: boolean;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 rounded-md border px-2 py-1",
        strong ? "border-line-strong bg-white/[0.04]" : "border-line bg-white/[0.02]",
      )}
    >
      <span className="text-[11px] text-fg-muted">{label}</span>
      <span className={cn("tabular font-mono text-[11.5px]", muted ? "text-fg-dim" : "text-fg")}>{value}</span>
    </span>
  );
}
