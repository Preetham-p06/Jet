"use client";

import { useRef } from "react";
import { motion, useInView } from "motion/react";
import { FileText, Mail, MessageSquare, Smartphone, type LucideIcon } from "lucide-react";
import { SectionHeader } from "@/components/ui/section-header";
import { FlightDefs, FlightPath } from "@/components/ui/flight-path";
import { LogoMark } from "@/components/ui/logo";
import { AnimatedNumber } from "@/components/ui/animated-number";
import { ConfidenceBadge } from "@/components/ui/confidence-badge";
import { ENGINE_STAGES, FRAGMENTS, RECOMMENDED, type FragmentKind } from "@/lib/demo-data";
import { enter } from "@/lib/animations";
import { cn } from "@/lib/utils";

const ICONS: Record<FragmentKind, LucideIcon> = {
  pdf: FileText,
  email: Mail,
  chat: MessageSquare,
  sms: Smartphone,
};

/* Stage coordinate system (desktop): 1180 × 420 */
const W = 1180;
const H = 420;
const CHIPS = [
  { x: 140, y: 60 },
  { x: 300, y: 118 },
  { x: 112, y: 192 },
  { x: 292, y: 252 },
  { x: 150, y: 322 },
  { x: 312, y: 380 },
];
const ENGINE = { cx: 640, cy: 210, w: 236 };
const DECISION = { cx: 1010, cy: 210, w: 268 };

function inputPath(p: { x: number; y: number }) {
  const x1 = p.x + 104;
  const y1 = p.y;
  const x2 = ENGINE.cx - ENGINE.w / 2;
  const y2 = ENGINE.cy + (p.y - ENGINE.cy) * 0.14;
  return `M${x1} ${y1} C ${x1 + 120} ${y1}, ${x2 - 120} ${y2}, ${x2} ${y2}`;
}
const OUTPUT_PATH = `M${ENGINE.cx + ENGINE.w / 2} ${ENGINE.cy} C ${ENGINE.cx + ENGINE.w / 2 + 70} ${ENGINE.cy}, ${
  DECISION.cx - DECISION.w / 2 - 70
} ${DECISION.cy}, ${DECISION.cx - DECISION.w / 2} ${DECISION.cy}`;

const FLOAT = ["animate-float-a", "animate-float-b", "animate-float-c"];

function Fragment({ i, className }: { i: number; className?: string }) {
  const f = FRAGMENTS[i];
  const Icon = ICONS[f.kind];
  return (
    <div
      className={cn(
        "glass flex w-[212px] max-w-full items-center gap-2.5 rounded-xl px-3 py-2 shadow-card",
        className,
      )}
    >
      <Icon className="h-3.5 w-3.5 shrink-0 text-fg-dim" aria-hidden="true" />
      <span className="min-w-0">
        <span className="block truncate text-[12px] text-fg">{f.text}</span>
        <span className="block truncate font-mono text-[10px] text-fg-dim">{f.meta}</span>
      </span>
    </div>
  );
}

function Engine({ active, className }: { active: boolean; className?: string }) {
  return (
    <div className={cn("glass-strong edge-light rounded-2xl p-4", className)}>
      <div className="flex items-center gap-2">
        <LogoMark className="h-4 w-4" />
        <span className="eyebrow text-[10px]">JetStream engine</span>
      </div>
      <ol className="mt-3 space-y-1.5">
        {ENGINE_STAGES.map((s, i) => (
          <li
            key={s}
            style={{ transitionDelay: active ? `${0.9 + i * 0.32}s` : "0s" }}
            className={cn(
              "flex items-center justify-between rounded-lg border px-2.5 py-1.5 font-mono text-[11px] uppercase tracking-[0.14em]",
              "transition-[color,border-color,background-color] duration-500 ease-out-expo",
              active ? "border-cyan/30 bg-cyan/[0.06] text-ice" : "border-line bg-white/[0.02] text-fg-dim",
            )}
          >
            {s}
            <span
              style={{ transitionDelay: active ? `${0.9 + i * 0.32}s` : "0s" }}
              className={cn(
                "h-1.5 w-1.5 rounded-full transition-[background-color,box-shadow] duration-500",
                active ? "bg-cyan shadow-[0_0_10px_rgba(89,217,255,0.8)]" : "bg-fg-dim/40",
              )}
              aria-hidden="true"
            />
          </li>
        ))}
      </ol>
    </div>
  );
}

function Decision({ active, className, delay = 2.2 }: { active: boolean; className?: string; delay?: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      animate={active ? { opacity: 1, y: 0 } : { opacity: 0, y: 14 }}
      transition={{ ...enter, delay }}
      className={cn(
        "relative rounded-2xl border border-cyan/30 bg-[linear-gradient(180deg,rgba(89,217,255,0.08),rgba(255,255,255,0.02))] p-4 shadow-[0_0_0_1px_rgba(89,217,255,0.12),0_30px_80px_-30px_rgba(89,217,255,0.45)]",
        className,
      )}
    >
      <span className="absolute -top-2.5 right-3 rounded-full border border-cyan/35 bg-[#0c1a24] px-2 py-0.5 font-mono text-[9.5px] tracking-[0.12em] text-cyan">
        RECOMMENDED
      </span>
      <p className="eyebrow text-[10px]">Clear decision</p>
      <p className="mt-2 text-[30px] font-semibold leading-none tracking-[-0.03em] text-fg">
        {active ? (
          <AnimatedNumber value={RECOMMENDED.trueCost} from={0} start="immediate" duration={1.4} delay={delay + 0.1} />
        ) : (
          "—"
        )}
      </p>
      <div className="mt-2.5 flex items-center gap-2">
        <ConfidenceBadge value={RECOMMENDED.finalFit} label="confidence" />
      </div>
      <p className="mt-3 text-[12.5px] text-fg-muted">
        {RECOMMENDED.aircraft} <span className="text-fg-dim">·</span> {RECOMMENDED.operator}
      </p>
    </motion.div>
  );
}

export function Problem() {
  const stageRef = useRef<HTMLDivElement>(null);
  const active = useInView(stageRef, { once: true, amount: 0.4 });

  return (
    <section id="product" className="relative py-24 sm:py-32">
      <div className="container-x">
        <SectionHeader
          eyebrow="The problem"
          title={
            <>
              The quote isn&rsquo;t the problem.
              <br className="hidden sm:block" /> The chaos around it is.
            </>
          }
          lead="Twelve operators reply twelve different ways. JetStream reads every one of them and routes what matters into a single, comparable decision."
        />
      </div>

      {/* ---------- desktop stage ---------- */}
      <div ref={stageRef} className="container-wide mt-14 hidden lg:block">
        <div className="relative" style={{ aspectRatio: `${W} / ${H}` }}>
          <svg
            viewBox={`0 0 ${W} ${H}`}
            preserveAspectRatio="none"
            className="absolute inset-0 h-full w-full"
            aria-hidden="true"
          >
            <FlightDefs id="pb" />
            {CHIPS.map((p, i) => (
              <FlightPath
                key={i}
                d={inputPath(p)}
                defsId="pb"
                strokeWidth={1.1}
                glow={false}
                dots={1}
                dotDuration={4.2 + i * 0.55}
                delay={0.1 + i * 0.12}
              />
            ))}
            <FlightPath
              d={OUTPUT_PATH}
              defsId="pb"
              strokeWidth={1.6}
              dots={2}
              dotDuration={2.6}
              delay={1.9}
            />
          </svg>

          {CHIPS.map((p, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, x: -12 }}
              animate={active ? { opacity: 1, x: 0 } : { opacity: 0, x: -12 }}
              transition={{ ...enter, delay: i * 0.08 }}
              className="absolute -translate-x-1/2 -translate-y-1/2"
              style={{ left: `${(p.x / W) * 100}%`, top: `${(p.y / H) * 100}%` }}
            >
              <Fragment i={i} className={cn(FLOAT[i % 3], "motion-reduce:animate-none")} />
            </motion.div>
          ))}

          <div
            className="absolute -translate-x-1/2 -translate-y-1/2"
            style={{ left: `${(ENGINE.cx / W) * 100}%`, top: `${(ENGINE.cy / H) * 100}%`, width: ENGINE.w }}
          >
            <Engine active={active} />
          </div>

          <div
            className="absolute -translate-x-1/2 -translate-y-1/2"
            style={{ left: `${(DECISION.cx / W) * 100}%`, top: `${(DECISION.cy / H) * 100}%`, width: DECISION.w }}
          >
            <Decision active={active} />
          </div>
        </div>

        <p className="mt-6 text-center font-mono text-[11px] tracking-[0.14em] text-fg-dim">
          MESSY OPERATOR REPLIES <span className="text-fg-muted">→</span> EXTRACT · NORMALIZE · VALIDATE · COMPARE{" "}
          <span className="text-fg-muted">→</span> ONE DECISION
        </p>
      </div>

      {/* ---------- stacked (mobile / tablet) ---------- */}
      <MobileStage />
    </section>
  );
}

function MobileStage() {
  const ref = useRef<HTMLDivElement>(null);
  const active = useInView(ref, { once: true, amount: 0.3 });
  return (
    <div ref={ref} className="container-x mt-12 lg:hidden">
      <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
        {FRAGMENTS.map((_, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 10 }}
            animate={active ? { opacity: 1, y: 0 } : {}}
            transition={{ ...enter, delay: i * 0.07 }}
          >
            <Fragment i={i} className="w-full" />
          </motion.div>
        ))}
      </div>
      <Connector />
      <Engine active={active} className="mx-auto max-w-sm" />
      <Connector />
      <Decision active={active} className="mx-auto max-w-sm" delay={1.8} />
    </div>
  );
}

function Connector() {
  return (
    <div className="relative mx-auto my-3 h-12 w-px bg-[linear-gradient(180deg,rgba(255,255,255,0.06),rgba(89,217,255,0.7),rgba(255,255,255,0.06))]">
      <span className="absolute left-1/2 top-1/2 h-1.5 w-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-ice shadow-[0_0_10px_rgba(221,248,255,0.9)]" />
    </div>
  );
}
