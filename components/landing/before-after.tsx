"use client";

import { useRef } from "react";
import { motion, useScroll, useSpring, useTransform } from "motion/react";
import { useReducedMotionSafe } from "@/lib/use-reduced-motion";
import { Check, FileText, Mail, MessageSquare, Table2 } from "lucide-react";
import { SectionHeader } from "@/components/ui/section-header";
import { Reveal, RevealGroup, RevealItem } from "@/components/ui/reveal";
import { ConfidenceBadge } from "@/components/ui/confidence-badge";
import { AFTER_ITEMS, BEFORE_ITEMS, QUOTES } from "@/lib/demo-data";
import { cn, formatUSD } from "@/lib/utils";

/* scattered "before" chips: position (%), rotation (deg) */
const SCATTER = [
  { x: 6, y: 18, r: -3 },
  { x: 46, y: 12, r: 2 },
  { x: 22, y: 38, r: 1.5 },
  { x: 58, y: 42, r: -2 },
  { x: 10, y: 64, r: 2.5 },
  { x: 40, y: 72, r: -1.5 },
];
const ICONS = [Mail, FileText, Table2, MessageSquare, Mail, FileText];

function BeforeLayer() {
  return (
    <div className="absolute inset-0 p-5 sm:p-6">
      {/* spreadsheet grid backdrop */}
      <div
        aria-hidden="true"
        className="absolute inset-0 opacity-[0.35] [background-image:linear-gradient(to_right,rgba(255,255,255,0.05)_1px,transparent_1px),linear-gradient(to_bottom,rgba(255,255,255,0.05)_1px,transparent_1px)] [background-size:96px_28px]"
      />
      <div className="relative flex items-center gap-3">
        <span className="rounded-full border border-amber/30 bg-amber/10 px-2 py-0.5 font-mono text-[10px] tracking-[0.14em] text-amber">
          BEFORE
        </span>
        <span className="font-mono text-[11px] text-fg-dim">12 replies · 1 spreadsheet · 3 follow-ups</span>
      </div>
      <ul className="relative mt-4 h-[calc(100%-2.5rem)]">
        {BEFORE_ITEMS.map((item, i) => {
          const Icon = ICONS[i];
          const s = SCATTER[i];
          return (
            <li
              key={item}
              className="absolute flex w-[44%] max-w-[300px] items-start gap-2.5 rounded-lg border border-line bg-surface-2/90 px-3 py-2.5 text-[12px] leading-snug text-fg-muted shadow-card"
              style={{ left: `${s.x}%`, top: `${s.y}%`, transform: `rotate(${s.r}deg)` }}
            >
              <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0 text-fg-dim" aria-hidden="true" />
              {item}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function AfterLayer() {
  return (
    <div className="absolute inset-0 bg-surface-2 p-5 sm:p-6">
      <div className="flex items-center gap-3">
        <span className="rounded-full border border-cyan/30 bg-cyan/10 px-2 py-0.5 font-mono text-[10px] tracking-[0.14em] text-cyan">
          AFTER
        </span>
        <span className="font-mono text-[11px] text-fg-dim">One workspace · normalized · verified</span>
      </div>
      <div className="mt-4 grid gap-5 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
        <table className="w-full border-separate border-spacing-0 text-[12px]">
          <thead>
            <tr className="font-mono text-[10px] uppercase tracking-[0.14em] text-fg-dim">
              <th className="pb-2 text-left font-normal">Aircraft</th>
              <th className="pb-2 text-right font-normal">Headline</th>
              <th className="pb-2 text-right font-normal">True cost</th>
              <th className="pb-2 text-right font-normal">Fit</th>
            </tr>
          </thead>
          <tbody>
            {QUOTES.map((q) => (
              <tr key={q.id} className={cn(q.recommended && "text-fg")}>
                <td className="border-t border-line py-2 pr-2">
                  <span className="block truncate text-fg">{q.aircraft}</span>
                  <span className="block truncate text-[10.5px] text-fg-dim">{q.operator}</span>
                </td>
                <td className="tabular border-t border-line py-2 text-right font-mono text-fg-muted">
                  {formatUSD(q.headline)}
                </td>
                <td className="tabular border-t border-line py-2 text-right font-mono text-fg">
                  {formatUSD(q.trueCost)}
                  {q.warning && <span className="text-amber">+</span>}
                </td>
                <td className="border-t border-line py-2 pl-2 text-right">
                  <ConfidenceBadge value={q.finalFit} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <ul className="hidden space-y-2 lg:block">
          {AFTER_ITEMS.map((item) => (
            <li key={item} className="flex items-start gap-2.5 text-[12.5px] leading-snug text-fg-muted">
              <span className="mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded-full bg-green/15 text-green">
                <Check className="h-2.5 w-2.5" strokeWidth={3} aria-hidden="true" />
              </span>
              {item}
            </li>
          ))}
        </ul>
      </div>
      <div className="absolute inset-x-5 bottom-5 grid grid-cols-3 gap-3 sm:inset-x-6 sm:bottom-6">
        {[
          ["Proposal", "ready to send"],
          ["Confidence", "97% on the recommendation"],
          ["Held for review", "1 flagged field"],
        ].map(([a, b]) => (
          <div key={a} className="rounded-lg border border-line bg-black/20 px-3 py-2.5">
            <p className="font-mono text-[9.5px] uppercase tracking-[0.14em] text-fg-dim">{a}</p>
            <p className="mt-1 text-[12px] text-fg">{b}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

export function BeforeAfter() {
  const ref = useRef<HTMLDivElement>(null);
  const reduce = useReducedMotionSafe();
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start 88%", "end 42%"] });
  const smooth = useSpring(scrollYProgress, { stiffness: 90, damping: 26, mass: 0.6 });
  const pct = useTransform(smooth, [0, 1], [12, 88]);
  const clip = useTransform(pct, (v) => `inset(0 ${100 - v}% 0 0)`);
  const left = useTransform(pct, (v) => `${v}%`);

  return (
    <section className="container-x py-12 sm:py-16">
      <SectionHeader
        eyebrow="Before / after"
        title="Same trip. A very different morning."
        lead="Scroll to watch twelve operator replies become one verified workspace."
      />

      {/* wipe panel (md+) */}
      <Reveal className="mt-12 hidden md:block">
        <div
          ref={ref}
          className="relative h-[460px] overflow-hidden rounded-2xl border border-line bg-surface"
        >
          <BeforeLayer />
          <motion.div
            style={reduce ? { clipPath: "inset(0 50% 0 0)" } : { clipPath: clip }}
            className="absolute inset-0"
          >
            <AfterLayer />
          </motion.div>
          <motion.div
            style={reduce ? { left: "50%" } : { left }}
            className="absolute inset-y-0 w-px bg-cyan shadow-[0_0_28px_rgba(89,217,255,0.9)]"
            aria-hidden="true"
          >
            <span className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full border border-cyan/40 bg-[#0c1a24] px-2 py-1 font-mono text-[9.5px] tracking-[0.14em] text-cyan shadow-[0_0_20px_rgba(89,217,255,0.5)]">
              JETSTREAM
            </span>
          </motion.div>
        </div>
      </Reveal>

      {/* stacked (mobile) */}
      <div className="mt-10 grid gap-4 md:hidden">
        <RevealGroup as="ul" className="rounded-2xl border border-line bg-surface p-4">
          <li className="mb-3 flex items-center gap-3">
            <span className="rounded-full border border-amber/30 bg-amber/10 px-2 py-0.5 font-mono text-[10px] tracking-[0.14em] text-amber">
              BEFORE
            </span>
            <span className="font-mono text-[11px] text-fg-dim">12 replies · 1 spreadsheet</span>
          </li>
          {BEFORE_ITEMS.map((item, i) => {
            const Icon = ICONS[i];
            return (
              <RevealItem as="li" key={item} className="flex items-start gap-2.5 py-1.5 text-[13px] text-fg-muted">
                <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0 text-fg-dim" aria-hidden="true" />
                {item}
              </RevealItem>
            );
          })}
        </RevealGroup>
        <RevealGroup as="ul" className="rounded-2xl border border-cyan/25 bg-surface-2 p-4">
          <li className="mb-3 flex items-center gap-3">
            <span className="rounded-full border border-cyan/30 bg-cyan/10 px-2 py-0.5 font-mono text-[10px] tracking-[0.14em] text-cyan">
              AFTER
            </span>
            <span className="font-mono text-[11px] text-fg-dim">One workspace</span>
          </li>
          {AFTER_ITEMS.map((item) => (
            <RevealItem as="li" key={item} className="flex items-start gap-2.5 py-1.5 text-[13px] text-fg-muted">
              <span className="mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded-full bg-green/15 text-green">
                <Check className="h-2.5 w-2.5" strokeWidth={3} aria-hidden="true" />
              </span>
              {item}
            </RevealItem>
          ))}
        </RevealGroup>
      </div>
    </section>
  );
}
