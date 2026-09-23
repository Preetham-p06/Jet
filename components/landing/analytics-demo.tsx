"use client";

import { useRef, type CSSProperties, type ReactNode } from "react";
import { useInView } from "motion/react";
import { SectionHeader } from "@/components/ui/section-header";
import { Reveal } from "@/components/ui/reveal";
import { LogoMark } from "@/components/ui/logo";
import { ANALYTICS } from "@/lib/demo-data";
import { cn } from "@/lib/utils";

/* One hue for magnitude; an ordinal ramp for ordered classes (validated). */
const HUE = "#5B8CFF";
const EMPHASIS = "#59D9FF";
const RAMP = ["#2A45B3", "#3F66E3", "#5B8CFF", "#8AB0FF"];
const MONTHS = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"];
const COST_BINS = [
  { label: "$25k", n: 2 },
  { label: "$30k", n: 5 },
  { label: "$35k", n: 9 },
  { label: "$40k", n: 14 },
  { label: "$45k", n: 11 },
  { label: "$50k", n: 7 },
  { label: "$55k", n: 4 },
  { label: "$60k+", n: 2 },
];

function grow(active: boolean, delay: number, axis: "x" | "y" = "y"): CSSProperties {
  return {
    transform: active ? "scale(1)" : axis === "y" ? "scaleY(0)" : "scaleX(0)",
    transformOrigin: axis === "y" ? "bottom" : "left",
    transformBox: "fill-box",
    transition: `transform 900ms cubic-bezier(0.16,1,0.3,1) ${delay}ms`,
  };
}

function Panel({
  title,
  sub,
  summary,
  className,
  children,
}: {
  title: string;
  sub: string;
  summary: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <figure
      aria-label={summary}
      className={cn("flex flex-col rounded-xl border border-line bg-white/[0.02] p-4", className)}
    >
      <figcaption>
        <p className="text-[13px] font-medium text-fg">{title}</p>
        <p className="text-[11px] text-fg-dim">{sub}</p>
      </figcaption>
      <div className="mt-4 flex-1">{children}</div>
    </figure>
  );
}

/* ---- 1 · quote volume (columns, emphasis on latest) ---- */
function QuoteVolume({ active }: { active: boolean }) {
  const v = ANALYTICS.quoteVolume;
  const max = Math.max(...v);
  const W = 240;
  const H = 96;
  const bw = 11;
  const gap = (W - v.length * bw) / (v.length - 1);
  return (
    <svg viewBox={`0 0 ${W} ${H + 14}`} className="h-auto w-full" role="img" aria-hidden="true">
      <line x1="0" x2={W} y1={H} y2={H} stroke="rgba(255,255,255,0.1)" />
      {v.map((n, i) => {
        const h = (n / max) * (H - 14);
        const x = i * (bw + gap);
        const last = i === v.length - 1;
        return (
          <g key={i}>
            <rect
              x={x}
              y={H - h}
              width={bw}
              height={h}
              rx="2"
              fill={last ? EMPHASIS : HUE}
              opacity={last ? 1 : 0.7}
              style={grow(active, i * 40)}
            >
              <title>{`${MONTHS[i]}: ${n} quotes`}</title>
            </rect>
            {last && (
              <text x={x + bw / 2} y={H - h - 5} textAnchor="middle" fontSize="9" fill="#DDF8FF" fontFamily="var(--font-mono)">
                {n}
              </text>
            )}
            <text x={x + bw / 2} y={H + 11} textAnchor="middle" fontSize="8" fill="#66717D" fontFamily="var(--font-mono)">
              {MONTHS[i]}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

/* ---- horizontal bar list (one hue) ---- */
function HBars({
  rows,
  active,
  format,
  ramp,
}: {
  rows: { label: string; value: number }[];
  active: boolean;
  format: (v: number) => string;
  ramp?: boolean;
}) {
  const max = Math.max(...rows.map((r) => r.value));
  return (
    <ul className="space-y-2.5">
      {rows.map((r, i) => (
        <li key={r.label} className="grid grid-cols-[92px_1fr_auto] items-center gap-3 text-[11.5px]">
          <span className="truncate text-fg-muted">{r.label}</span>
          <span className="h-2 overflow-hidden rounded-full bg-white/[0.05]">
            <span
              className="block h-full rounded-full"
              style={{
                width: `${(r.value / max) * 100}%`,
                background: ramp ? RAMP[Math.min(RAMP.length - 1, i)] : HUE,
                transform: active ? "scaleX(1)" : "scaleX(0)",
                transformOrigin: "left",
                transition: `transform 900ms cubic-bezier(0.16,1,0.3,1) ${120 + i * 90}ms`,
              }}
              title={`${r.label}: ${format(r.value)}`}
            />
          </span>
          <span className="tabular font-mono text-[11px] text-fg">{format(r.value)}</span>
        </li>
      ))}
    </ul>
  );
}

/* ---- cost distribution (histogram) ---- */
function CostDistribution({ active }: { active: boolean }) {
  const max = Math.max(...COST_BINS.map((b) => b.n));
  const W = 240;
  const H = 96;
  const bw = 24;
  const gap = (W - COST_BINS.length * bw) / (COST_BINS.length - 1);
  return (
    <svg viewBox={`0 0 ${W} ${H + 14}`} className="h-auto w-full" role="img" aria-hidden="true">
      <line x1="0" x2={W} y1={H} y2={H} stroke="rgba(255,255,255,0.1)" />
      {COST_BINS.map((b, i) => {
        const h = (b.n / max) * (H - 14);
        const x = i * (bw + gap);
        return (
          <g key={b.label}>
            <rect x={x} y={H - h} width={bw} height={h} rx="2" fill={HUE} opacity="0.75" style={grow(active, i * 50)}>
              <title>{`${b.label}: ${b.n} quotes`}</title>
            </rect>
            <text x={x + bw / 2} y={H + 11} textAnchor="middle" fontSize="8" fill="#66717D" fontFamily="var(--font-mono)">
              {b.label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

/* ---- aircraft mix (ordinal stacked bar) ---- */
function AircraftMix({ active }: { active: boolean }) {
  const order = ["Light", "Midsize", "Super-mid", "Heavy"];
  const rows = order.map((l) => ANALYTICS.aircraftMix.find((m) => m.label === l)!);
  return (
    <div>
      <div className="flex h-3 w-full gap-0.5 overflow-hidden rounded-full">
        {rows.map((r, i) => (
          <span
            key={r.label}
            className="block h-full first:rounded-l-full last:rounded-r-full"
            style={{
              width: `${r.pct}%`,
              background: RAMP[i],
              transform: active ? "scaleX(1)" : "scaleX(0)",
              transformOrigin: "left",
              transition: `transform 900ms cubic-bezier(0.16,1,0.3,1) ${i * 110}ms`,
            }}
            title={`${r.label}: ${r.pct}%`}
          />
        ))}
      </div>
      <ul className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1.5 text-[11.5px]">
        {rows.map((r, i) => (
          <li key={r.label} className="flex items-center gap-2 text-fg-muted">
            <span className="h-2 w-2 rounded-sm" style={{ background: RAMP[i] }} aria-hidden="true" />
            {r.label}
            <span className="tabular ml-auto font-mono text-[11px] text-fg">{r.pct}%</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function AnalyticsDemo() {
  const ref = useRef<HTMLDivElement>(null);
  const active = useInView(ref, { once: true, amount: 0.3 });
  const f = ANALYTICS.funnel;

  return (
    <section className="container-x py-24 sm:py-32">
      <SectionHeader
        eyebrow="Operations"
        title="Every normalized quote becomes operational insight."
        lead="A sample of the analytics workspace JetStream can grow into. Operator behaviour, fee patterns and conversion, all derived from quotes brokers already receive."
      />

      <Reveal className="mt-12">
        <div ref={ref} className="glass-strong edge-light overflow-hidden rounded-2xl shadow-shell">
          <div className="flex h-11 items-center justify-between border-b border-line px-4">
            <div className="flex items-center gap-2.5">
              <LogoMark className="h-4 w-4" />
              <span className="whitespace-nowrap font-mono text-[11px] tracking-[0.14em] text-fg-muted">
                JETSTREAM <span className="text-fg-dim">/</span> ANALYTICS
              </span>
            </div>
            <span className="whitespace-nowrap rounded-md border border-amber/30 bg-amber/[0.06] px-2 py-0.5 font-mono text-[9.5px] tracking-[0.12em] text-amber">
              SAMPLE<span className="hidden sm:inline"> WORKSPACE</span> DATA
            </span>
          </div>

          <div className="grid gap-3 p-3 sm:grid-cols-2 sm:p-4 lg:grid-cols-3">
            <Panel
              title="Quote volume"
              sub="Normalized quotes per month, trailing 12"
              summary="Quote volume rises from 12 to 38 normalized quotes per month over the trailing twelve months."
            >
              <QuoteVolume active={active} />
            </Panel>
            <Panel
              title="Operator response time"
              sub="Median hours from request to first quote"
              summary="Median operator response time ranges from 1.4 hours for Atlas Air Charter to 5.2 hours for Summit Executive."
            >
              <HBars
                active={active}
                rows={ANALYTICS.responseTimes.map((r) => ({ label: r.operator, value: r.hours }))}
                format={(v) => `${v.toFixed(1)}h`}
              />
            </Panel>
            <Panel
              title="Cost distribution"
              sub="True cost of normalized quotes, this quarter"
              summary="True quote costs cluster between forty and forty-five thousand dollars."
            >
              <CostDistribution active={active} />
            </Panel>
            <Panel
              title="Common fee types"
              sub="Share of quotes carrying each added charge"
              summary="Positioning appears in 84 percent of quotes, ramp or handling in 71 percent, fuel surcharge in 46 percent."
            >
              <HBars
                active={active}
                rows={ANALYTICS.feeTypes.map((r) => ({ label: r.label, value: r.pct }))}
                format={(v) => `${v}%`}
              />
            </Panel>
            <Panel
              title="Aircraft preference"
              sub="Share of booked trips by category"
              summary="Midsize aircraft account for 38 percent of booked trips, super-midsize 34, heavy 18, light 10."
            >
              <AircraftMix active={active} />
            </Panel>
            <Panel
              title="Conversion funnel"
              sub="Requests to booked trips, this quarter"
              summary="Of 120 requests, 96 received quotes, 64 became proposals and 22 were booked."
            >
              <HBars
                active={active}
                rows={f.map((r) => ({ label: r.label, value: r.value }))}
                format={(v) => String(v)}
                ramp
              />
            </Panel>
          </div>
        </div>
      </Reveal>
    </section>
  );
}
