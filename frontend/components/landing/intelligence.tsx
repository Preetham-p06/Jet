"use client";

import { useRef } from "react";
import { motion, useInView } from "motion/react";
import { Check } from "lucide-react";
import { SectionHeader } from "@/components/ui/section-header";
import { FlightDefs, FlightPath } from "@/components/ui/flight-path";
import { LogoMark } from "@/components/ui/logo";
import { AnimatedNumber } from "@/components/ui/animated-number";
import { ConfidenceBadge } from "@/components/ui/confidence-badge";
import { RECOMMENDATION_CHECKS, RECOMMENDED, SIGNALS } from "@/lib/demo-data";
import { enter } from "@/lib/animations";
import { cn } from "@/lib/utils";

/* Stage coordinate system (desktop): 1180 × 460 */
const W = 1180;
const H = 460;
const SIGNAL_X = 150;
const SIGNAL_W = 196;
const NODE = { cx: 590, cy: 230, r: 46 };
const CARD = { cx: 985, cy: 230, w: 312 };

const signalY = (i: number) => 44 + i * 53;

function inputPath(i: number) {
  const x1 = SIGNAL_X + SIGNAL_W / 2;
  const y1 = signalY(i);
  const x2 = NODE.cx - NODE.r - 2;
  const y2 = NODE.cy + (y1 - NODE.cy) * 0.08;
  return `M${x1} ${y1} C ${x1 + 130} ${y1}, ${x2 - 110} ${y2}, ${x2} ${y2}`;
}
const OUTPUT = `M${NODE.cx + NODE.r + 2} ${NODE.cy} L ${CARD.cx - CARD.w / 2} ${CARD.cy}`;

function Signal({ label, className }: { label: string; className?: string }) {
  return (
    <div
      className={cn(
        "flex items-center justify-between gap-2 rounded-lg border border-line bg-white/[0.03] px-3 py-2 text-[12.5px] text-fg-muted",
        className,
      )}
    >
      {label}
      <span className="h-1 w-1 rounded-full bg-cyan/70" aria-hidden="true" />
    </div>
  );
}

function Node({ active, className }: { active: boolean; className?: string }) {
  return (
    <div className={cn("relative grid place-items-center", className)} style={{ width: NODE.r * 2, height: NODE.r * 2 }}>
      <span
        aria-hidden="true"
        className={cn(
          "absolute inset-0 rounded-full border border-cyan/30 transition-[box-shadow,border-color] duration-1000",
          active && "border-cyan/60 shadow-[0_0_60px_rgba(89,217,255,0.35),inset_0_0_30px_rgba(89,217,255,0.15)]",
        )}
      />
      <span
        aria-hidden="true"
        className="absolute -inset-3 rounded-full border border-cyan/10 motion-safe:animate-[pulse_3s_ease-in-out_infinite]"
      />
      <span className="glass-strong grid h-full w-full place-items-center rounded-full">
        <LogoMark className="h-7 w-7" />
      </span>
    </div>
  );
}

function Recommendation({ active, className, delay = 1.6 }: { active: boolean; className?: string; delay?: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      animate={active ? { opacity: 1, y: 0 } : { opacity: 0, y: 14 }}
      transition={{ ...enter, delay }}
      className={cn("glass-strong edge-light rounded-2xl p-5", className)}
    >
      <div className="flex items-center justify-between">
        <p className="eyebrow text-[10px]">Recommendation</p>
        <span className="rounded-md border border-line px-1.5 py-0.5 font-mono text-[9.5px] tracking-[0.12em] text-fg-dim">
          DEMO DATA
        </span>
      </div>
      <p className="mt-3 text-[12.5px] text-fg-muted">Best fit for this trip</p>
      <p className="mt-1 text-[22px] font-semibold tracking-[-0.02em] text-fg">{RECOMMENDED.aircraft}</p>
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5">
        <span className="tabular text-[15px] text-fg">
          {active ? (
            <AnimatedNumber value={RECOMMENDED.trueCost} from={0} start="immediate" duration={1.2} delay={delay} />
          ) : (
            "—"
          )}{" "}
          <span className="text-[12px] text-fg-dim">estimated true cost</span>
        </span>
        <ConfidenceBadge value={RECOMMENDED.finalFit} label="fit" />
      </div>
      <ul className="mt-4 space-y-1.5 border-t border-line pt-4">
        {RECOMMENDATION_CHECKS.map((c, i) => (
          <motion.li
            key={c}
            initial={{ opacity: 0, x: -6 }}
            animate={active ? { opacity: 1, x: 0 } : {}}
            transition={{ ...enter, delay: delay + 0.3 + i * 0.12 }}
            className="flex items-center gap-2.5 text-[12.5px] text-fg-muted"
          >
            <span className="grid h-4 w-4 shrink-0 place-items-center rounded-full bg-green/15 text-green">
              <Check className="h-2.5 w-2.5" strokeWidth={3} aria-hidden="true" />
            </span>
            {c}
          </motion.li>
        ))}
      </ul>
    </motion.div>
  );
}

export function Intelligence() {
  const stageRef = useRef<HTMLDivElement>(null);
  const active = useInView(stageRef, { once: true, amount: 0.4 });
  const mobileRef = useRef<HTMLDivElement>(null);
  const mobileActive = useInView(mobileRef, { once: true, amount: 0.3 });

  return (
    <section id="intelligence" className="relative py-24 sm:py-32">
      <div className="container-x">
        <SectionHeader
          align="center"
          eyebrow="Intelligence"
          title="Not just extraction. Understanding."
          lead="Eight signals from every reply, weighed together against the trip and the client, so the recommendation is about the whole flight, not just the cheapest line."
        />
      </div>

      {/* desktop stage */}
      <div ref={stageRef} className="container-wide mt-14 hidden lg:block">
        <div className="relative" style={{ aspectRatio: `${W} / ${H}` }}>
          <svg
            viewBox={`0 0 ${W} ${H}`}
            preserveAspectRatio="none"
            className="absolute inset-0 h-full w-full"
            aria-hidden="true"
          >
            <FlightDefs id="in" />
            {SIGNALS.map((_, i) => (
              <FlightPath
                key={i}
                d={inputPath(i)}
                defsId="in"
                strokeWidth={1.1}
                glow={false}
                dots={1}
                dotDuration={3.6 + (i % 4) * 0.7}
                delay={0.1 + i * 0.08}
              />
            ))}
            <FlightPath d={OUTPUT} defsId="in" strokeWidth={1.6} dots={2} dotDuration={2.4} delay={1.3} />
          </svg>

          {SIGNALS.map((s, i) => (
            <motion.div
              key={s}
              initial={{ opacity: 0, x: -10 }}
              animate={active ? { opacity: 1, x: 0 } : { opacity: 0, x: -10 }}
              transition={{ ...enter, delay: i * 0.06 }}
              className="absolute -translate-x-1/2 -translate-y-1/2"
              style={{ left: `${(SIGNAL_X / W) * 100}%`, top: `${(signalY(i) / H) * 100}%`, width: SIGNAL_W }}
            >
              <Signal label={s} />
            </motion.div>
          ))}

          <div
            className="absolute -translate-x-1/2 -translate-y-1/2"
            style={{ left: `${(NODE.cx / W) * 100}%`, top: `${(NODE.cy / H) * 100}%` }}
          >
            <Node active={active} />
            <p className="absolute left-1/2 top-full mt-3 -translate-x-1/2 whitespace-nowrap font-mono text-[10px] tracking-[0.16em] text-fg-dim">
              JETSTREAM
            </p>
          </div>

          <div
            className="absolute -translate-x-1/2 -translate-y-1/2"
            style={{ left: `${(CARD.cx / W) * 100}%`, top: `${(CARD.cy / H) * 100}%`, width: CARD.w }}
          >
            <Recommendation active={active} />
          </div>
        </div>
      </div>

      {/* stacked */}
      <div ref={mobileRef} className="container-x mt-12 lg:hidden">
        <div className="grid grid-cols-2 gap-2">
          {SIGNALS.map((s, i) => (
            <motion.div
              key={s}
              initial={{ opacity: 0, y: 8 }}
              animate={mobileActive ? { opacity: 1, y: 0 } : {}}
              transition={{ ...enter, delay: i * 0.05 }}
            >
              <Signal label={s} />
            </motion.div>
          ))}
        </div>
        <div className="my-4 flex flex-col items-center">
          <span className="h-10 w-px bg-[linear-gradient(180deg,rgba(255,255,255,0.06),rgba(89,217,255,0.7))]" />
          <Node active={mobileActive} />
          <span className="h-10 w-px bg-[linear-gradient(180deg,rgba(89,217,255,0.7),rgba(255,255,255,0.06))]" />
        </div>
        <Recommendation active={mobileActive} className="mx-auto max-w-sm" delay={0.8} />
      </div>
    </section>
  );
}
