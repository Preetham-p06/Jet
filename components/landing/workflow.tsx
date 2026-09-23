"use client";

import { useEffect, useRef, useState } from "react";
import { motion, useMotionValueEvent, useScroll, useSpring } from "motion/react";
import { SectionHeader } from "@/components/ui/section-header";
import { FlightDefs, FlightPath } from "@/components/ui/flight-path";
import { WORKFLOW_STAGES } from "@/lib/demo-data";
import { useReducedMotionSafe } from "@/lib/use-reduced-motion";
import { cn } from "@/lib/utils";

const W = 1180;
const H = 200;
const PATH = "M30 140 C 220 30, 400 200, 590 100 S 960 20, 1150 120";
const COLUMN_X = WORKFLOW_STAGES.map((_, i) => (W / WORKFLOW_STAGES.length) * (i + 0.5));

export function Workflow() {
  const ref = useRef<HTMLDivElement>(null);
  const measureRef = useRef<SVGPathElement>(null);
  const reduce = useReducedMotionSafe();
  const [nodes, setNodes] = useState<{ x: number; y: number }[]>([]);
  const [litByScroll, setLit] = useState(0);
  const lit = reduce ? WORKFLOW_STAGES.length : litByScroll;

  useEffect(() => {
    const p = measureRef.current;
    if (!p) return;
    const len = p.getTotalLength();
    const samples = 300;
    const pts = Array.from({ length: samples + 1 }, (_, i) => p.getPointAtLength((len * i) / samples));
    setNodes(
      COLUMN_X.map((tx) => pts.reduce((best, pt) => (Math.abs(pt.x - tx) < Math.abs(best.x - tx) ? pt : best))),
    );
  }, []);

  const { scrollYProgress } = useScroll({ target: ref, offset: ["start 82%", "end 58%"] });
  const progress = useSpring(scrollYProgress, { stiffness: 70, damping: 22, mass: 0.6 });
  useMotionValueEvent(progress, "change", (v) => {
    setLit(Math.min(WORKFLOW_STAGES.length, Math.floor(v * WORKFLOW_STAGES.length + 0.55)));
  });

  return (
    <section id="how-it-works" className="container-x py-24 sm:py-32">
      <SectionHeader
        align="center"
        eyebrow="How it works"
        title="From request to proposal, without the spreadsheet marathon."
        lead="Five stages. One flight path. The broker types the request; JetStream does the reading."
      />

      <div ref={ref} className="mt-14">
        {/* desktop: horizontal flight path */}
        <div className="hidden md:block">
          <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full overflow-visible" aria-hidden="true">
            <FlightDefs id="wf" />
            <path ref={measureRef} d={PATH} fill="none" stroke="none" />
            <FlightPath
              d={PATH}
              defsId="wf"
              progress={reduce ? 1 : progress}
              strokeWidth={2}
              dots={reduce ? 0 : 2}
              dotDuration={7}
            />
            {nodes.map((n, i) => {
              const on = i < lit;
              return (
                <g key={i} transform={`translate(${n.x} ${n.y})`}>
                  <circle
                    r="16"
                    className={cn("transition-[fill] duration-500", on ? "fill-cyan/15" : "fill-transparent")}
                  />
                  <circle
                    r="6"
                    className={cn(
                      "transition-[fill,stroke] duration-500",
                      on ? "fill-ice stroke-cyan" : "fill-[#0d121a] stroke-white/25",
                    )}
                    strokeWidth="1.5"
                    style={on ? { filter: "drop-shadow(0 0 8px rgba(89,217,255,0.9))" } : undefined}
                  />
                </g>
              );
            })}
          </svg>

          <ol className="mt-4 grid grid-cols-5 gap-4">
            {WORKFLOW_STAGES.map((s, i) => {
              const on = i < lit;
              return (
                <li key={s.n} className="px-1 text-center">
                  <p className={cn("font-mono text-[10px] tracking-[0.16em] transition-colors duration-500", on ? "text-cyan" : "text-fg-dim")}>
                    {s.n}
                  </p>
                  <h3 className={cn("mt-1.5 text-[16px] font-semibold tracking-[-0.01em] transition-colors duration-500", on ? "text-fg" : "text-fg-dim")}>
                    {s.title}
                  </h3>
                  <p className={cn("mt-1 text-[12.5px] leading-snug transition-colors duration-500", on ? "text-fg-muted" : "text-fg-dim")}>
                    {s.detail}
                  </p>
                </li>
              );
            })}
          </ol>
        </div>

        {/* mobile: vertical rail */}
        <ol className="relative md:hidden">
          <span aria-hidden="true" className="absolute bottom-3 left-[11px] top-3 w-px bg-white/10" />
          <motion.span
            aria-hidden="true"
            style={{ scaleY: reduce ? 1 : progress }}
            className="absolute bottom-3 left-[11px] top-3 w-px origin-top bg-[linear-gradient(180deg,#5B8CFF,#59D9FF)] shadow-[0_0_12px_rgba(89,217,255,0.6)]"
          />
          {WORKFLOW_STAGES.map((s, i) => {
            const on = i < lit;
            return (
              <li key={s.n} className="relative flex gap-5 py-4 pl-9">
                <span
                  aria-hidden="true"
                  className={cn(
                    "absolute left-[6px] top-[26px] h-[11px] w-[11px] rounded-full border transition-[background-color,border-color,box-shadow] duration-500",
                    on ? "border-cyan bg-ice shadow-[0_0_10px_rgba(89,217,255,0.9)]" : "border-white/25 bg-[#0d121a]",
                  )}
                />
                <div>
                  <p className={cn("font-mono text-[10px] tracking-[0.16em]", on ? "text-cyan" : "text-fg-dim")}>{s.n}</p>
                  <h3 className={cn("mt-1 text-[16px] font-semibold", on ? "text-fg" : "text-fg-dim")}>{s.title}</h3>
                  <p className={cn("mt-1 text-[13px]", on ? "text-fg-muted" : "text-fg-dim")}>{s.detail}</p>
                </div>
              </li>
            );
          })}
        </ol>
      </div>
    </section>
  );
}
