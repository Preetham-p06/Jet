"use client";

import { useState, type ReactNode } from "react";
import { endpoints, type AnalyticsOverview } from "@/lib/api/endpoints";
import { useApi } from "@/lib/api/hooks";
import { cn } from "@/lib/utils";
import { formatCents, fmtHours } from "../fmt";
import { EmptyState, ErrorState, LoadingBlock, Segmented } from "../ui";

/* Palette matches components/landing/analytics-demo.tsx: one hue for magnitude,
   cyan for the emphasised mark, amber reserved for "lower bound" (not fully priced). */
const HUE = "#5B8CFF";
const EMPHASIS = "#59D9FF";
const LOWER = "#F6B95B";
const AXIS = "rgba(255,255,255,0.1)";
const INK_MUTED = "#7b8794";

type Range = "3" | "6" | "12";

function isoDate(d: Date) {
  return d.toISOString().slice(0, 10);
}

export function AnalyticsView() {
  const [range, setRange] = useState<Range>("12");
  const data = useApi(`analytics:${range}`, () => {
    const to = new Date();
    const from = new Date(to);
    from.setMonth(from.getMonth() - Number(range));
    return endpoints.analytics({ date_from: isoDate(from), date_to: isoDate(to) });
  });

  return (
    <div className="mt-8 flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-3">
        <Segmented
          label="Date range"
          value={range}
          onChange={setRange}
          options={[
            { value: "3", label: "3 months" },
            { value: "6", label: "6 months" },
            { value: "12", label: "12 months" },
          ]}
        />
        {data.data && (
          <span className="text-xs text-fg-dim">
            {data.data.date_from} → {data.data.date_to}
          </span>
        )}
      </div>

      {data.loading ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }, (_, i) => (
            <div key={i} className="surface-card rounded-2xl p-5">
              <LoadingBlock rows={4} />
            </div>
          ))}
        </div>
      ) : data.error && !data.data ? (
        <ErrorState error={data.error} onRetry={data.reload} />
      ) : data.data ? (
        <div className={cn("grid gap-4 md:grid-cols-2 xl:grid-cols-3 transition-opacity", data.refreshing && "opacity-60")}>
          <Panels d={data.data} />
        </div>
      ) : null}
    </div>
  );
}

function Panels({ d }: { d: AnalyticsOverview }) {
  const qv = d.quote_volume.items;
  const rt = d.response_times;
  const tc = d.true_cost_distribution;
  const f = d.funnel;
  return (
    <>
      <ChartPanel
        title="Quote volume"
        sub="Active quotes received per month"
        headline={qv.reduce((s, m) => s + m.count, 0).toLocaleString("en-US")}
        headlineLabel="quotes"
        empty={!qv.length}
        table={{ head: ["Month", "Quotes"], rows: qv.map((m) => [m.month, String(m.count)]) }}
      >
        <Columns
          items={qv.map((m) => ({ label: monthLabel(m.month), full: m.month, value: m.count }))}
          format={(v) => `${v} quotes`}
        />
      </ChartPanel>

      <ChartPanel
        title="Operator response time"
        sub="Median hours from RFQ to reply"
        headline={fmtHours(rt.median_hours)}
        headlineLabel={`median · n=${rt.n}`}
        empty={!rt.operators.length}
        table={{ head: ["Operator", "Median", "n"], rows: rt.operators.map((o) => [o.operator_name, fmtHours(o.median_hours), String(o.n)]) }}
      >
        <HBars
          rows={[...rt.operators].sort((a, b) => a.median_hours - b.median_hours).slice(0, 8).map((o) => ({ label: o.operator_name, value: o.median_hours, note: `n=${o.n}` }))}
          format={(v) => fmtHours(v)}
        />
      </ChartPanel>

      <ChartPanel
        title="True cost distribution"
        sub={`Known totals in ${formatCents(tc.bin_size_cents ?? 500000)} bins`}
        headline={formatCents(tc.median_cents)}
        headlineLabel={`median · p25 ${formatCents(tc.p25_cents)} · p75 ${formatCents(tc.p75_cents)}`}
        empty={!tc.bins.length}
        legend={
          <>
            <LegendKey color={HUE} label="Fully priced" />
            <LegendKey color={LOWER} label="Lower bound (+)" />
          </>
        }
        table={{
          head: ["Range", "Quotes", "Lower bound"],
          rows: tc.bins.map((b) => [`${formatCents(b.lower_cents)}–${formatCents(b.upper_cents)}`, String(b.count), String(b.lower_bound_count)]),
        }}
      >
        <Histogram bins={tc.bins} median={tc.median_cents} />
      </ChartPanel>

      <ChartPanel
        title="Fee types"
        sub="Share of quotes with each extra charge"
        empty={!d.fee_types.items.length}
        headline={String(d.fee_types.n_quotes)}
        headlineLabel="quotes analysed"
        table={{ head: ["Fee", "Share", "Quotes"], rows: d.fee_types.items.map((i) => [i.label, `${i.share_pct.toFixed(0)}%`, String(i.count)]) }}
      >
        <HBars
          rows={[...d.fee_types.items].sort((a, b) => b.share_pct - a.share_pct).slice(0, 8).map((i) => ({ label: i.label, value: i.share_pct, note: `${i.count}` }))}
          format={(v) => `${v.toFixed(0)}%`}
          max={100}
        />
      </ChartPanel>

      <ChartPanel
        title="Aircraft category mix"
        sub="Share of quotes by category"
        empty={!d.aircraft_mix.items.length}
        headline={String(d.aircraft_mix.n_quotes)}
        headlineLabel="quotes"
        table={{ head: ["Category", "Share", "Quotes"], rows: d.aircraft_mix.items.map((i) => [i.label, `${i.share_pct.toFixed(0)}%`, String(i.count)]) }}
      >
        <HBars
          rows={[...d.aircraft_mix.items].sort((a, b) => b.share_pct - a.share_pct).map((i) => ({ label: i.label, value: i.share_pct, note: `${i.count}` }))}
          format={(v) => `${v.toFixed(0)}%`}
          max={100}
        />
      </ChartPanel>

      <ChartPanel
        title="Trip funnel"
        sub="Trips created → quoted → proposal sent → booked"
        headline={f.created ? `${Math.round((f.booked / f.created) * 100)}%` : "—"}
        headlineLabel="booked of created"
        empty={f.created === 0}
        table={{
          head: ["Stage", "Trips"],
          rows: [
            ["Created", String(f.created)],
            ["Quoted", String(f.quoted)],
            ["Proposal sent", String(f.proposal_sent)],
            ["Booked", String(f.booked)],
          ],
        }}
      >
        <Funnel
          stages={[
            { label: "Created", value: f.created },
            { label: "Quoted", value: f.quoted },
            { label: "Proposal sent", value: f.proposal_sent },
            { label: "Booked", value: f.booked },
          ]}
        />
      </ChartPanel>
    </>
  );
}

function monthLabel(m: string) {
  const d = new Date(`${m.slice(0, 7)}-01T12:00:00`);
  return Number.isNaN(d.getTime()) ? m : d.toLocaleString("en-US", { month: "short" });
}

/* ------------------------------------------------------------------ */
/* Panel chrome with data-table fallback                               */
/* ------------------------------------------------------------------ */
function ChartPanel({
  title,
  sub,
  headline,
  headlineLabel,
  legend,
  table,
  empty,
  children,
}: {
  title: string;
  sub: string;
  headline?: string;
  headlineLabel?: string;
  legend?: ReactNode;
  table: { head: string[]; rows: string[][] };
  empty?: boolean;
  children: ReactNode;
}) {
  return (
    <figure className="surface-card flex min-w-0 flex-col rounded-2xl p-5">
      <figcaption className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[14px] font-medium text-fg">{title}</p>
          <p className="text-[11.5px] text-fg-dim">{sub}</p>
        </div>
        {headline && !empty && (
          <div className="shrink-0 text-right">
            <p className="tabular font-mono text-[20px] font-semibold leading-none text-fg">{headline}</p>
            {headlineLabel && <p className="mt-1 max-w-[150px] text-[10.5px] leading-tight text-fg-dim">{headlineLabel}</p>}
          </div>
        )}
      </figcaption>
      {empty ? (
        <EmptyState className="py-8" title="No data in this range" />
      ) : (
        <>
          <div className="relative mt-5 flex-1">{children}</div>
          {legend && <div className="mt-3 flex flex-wrap gap-4">{legend}</div>}
          <details className="mt-4 text-[12px]">
            <summary className="cursor-pointer select-none text-fg-dim hover:text-fg">Show data</summary>
            <table className="mt-2 w-full text-left">
              <thead>
                <tr>
                  {table.head.map((h) => (
                    <th key={h} className="border-b border-line pb-1 font-mono text-[10px] font-normal uppercase tracking-[0.12em] text-fg-dim">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {table.rows.map((r, i) => (
                  <tr key={i}>
                    {r.map((c, j) => (
                      <td key={j} className="tabular border-b border-line py-1 text-fg-muted">
                        {c}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        </>
      )}
    </figure>
  );
}

function LegendKey({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-[11px] text-fg-muted">
      <span aria-hidden="true" className="h-2.5 w-2.5 rounded-[3px]" style={{ background: color }} />
      {label}
    </span>
  );
}

/** Tooltip shared by the SVG charts: value first, label second. */
function Tip({ x, y, value, label }: { x: number; y: number; value: string; label: string }) {
  return (
    <div
      role="tooltip"
      className="glass-strong pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-full whitespace-nowrap rounded-lg px-2.5 py-1.5 text-center shadow-card"
      style={{ left: `${x}%`, top: `calc(${y}% - 8px)` }}
    >
      <p className="tabular font-mono text-[12px] font-semibold text-fg">{value}</p>
      <p className="text-[10.5px] text-fg-dim">{label}</p>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Columns (quote volume)                                              */
/* ------------------------------------------------------------------ */
function Columns({ items, format }: { items: { label: string; full: string; value: number }[]; format: (v: number) => string }) {
  const [hover, setHover] = useState<number | null>(null);
  const W = 300;
  const H = 120;
  const max = Math.max(1, ...items.map((i) => i.value));
  const slot = W / items.length;
  const bw = Math.min(18, slot - 4);
  const last = items.length - 1;
  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H + 16}`} className="h-auto w-full" role="img" aria-label={`Quote volume by month, latest ${items[last]?.value ?? 0}`}>
        <line x1="0" x2={W} y1={H} y2={H} stroke={AXIS} />
        {items.map((it, i) => {
          const h = Math.max(it.value ? 3 : 0, (it.value / max) * (H - 16));
          const x = i * slot + (slot - bw) / 2;
          const emph = i === last;
          return (
            <g key={it.full} onPointerEnter={() => setHover(i)} onPointerLeave={() => setHover(null)} onFocus={() => setHover(i)} onBlur={() => setHover(null)} tabIndex={0}>
              <rect x={i * slot} y={0} width={slot} height={H} fill="transparent" />
              <path d={roundTop(x, H - h, bw, h, 3)} fill={emph ? EMPHASIS : HUE} opacity={hover === null || hover === i ? (emph ? 1 : 0.8) : 0.45} />
              {emph && (
                <text x={x + bw / 2} y={H - h - 5} textAnchor="middle" fontSize="9" fill="#DDF8FF" fontFamily="var(--font-mono)">
                  {it.value}
                </text>
              )}
              {(items.length <= 12 || i % 2 === 0) && (
                <text x={x + bw / 2} y={H + 12} textAnchor="middle" fontSize="8" fill={INK_MUTED} fontFamily="var(--font-mono)">
                  {it.label}
                </text>
              )}
            </g>
          );
        })}
      </svg>
      {hover !== null && items[hover] && (
        <Tip
          x={((hover + 0.5) * slot * 100) / W}
          y={(((H - (items[hover].value / max) * (H - 16)) / (H + 16)) * 100)}
          value={format(items[hover].value)}
          label={items[hover].full}
        />
      )}
    </div>
  );
}

/** Rect with 4px-ish rounded top corners, square at the baseline. */
function roundTop(x: number, y: number, w: number, h: number, r: number) {
  if (h <= 0) return "";
  const rr = Math.min(r, w / 2, h);
  return `M${x},${y + h} V${y + rr} Q${x},${y} ${x + rr},${y} H${x + w - rr} Q${x + w},${y} ${x + w},${y + rr} V${y + h} Z`;
}

/* ------------------------------------------------------------------ */
/* Histogram with lower-bound stack (true cost)                        */
/* ------------------------------------------------------------------ */
function Histogram({
  bins,
  median,
}: {
  bins: { lower_cents: number; upper_cents: number; count: number; lower_bound_count: number }[];
  median: number | null;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const W = 300;
  const H = 120;
  const max = Math.max(1, ...bins.map((b) => b.count));
  const slot = W / bins.length;
  const bw = slot - 2;
  const lo = bins[0]?.lower_cents ?? 0;
  const hi = bins[bins.length - 1]?.upper_cents ?? 1;
  const mx = median != null ? ((median - lo) / Math.max(1, hi - lo)) * W : null;
  const k = (c: number) => `$${Math.round(c / 100000)}k`;
  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H + 16}`} className="h-auto w-full" role="img" aria-label="Histogram of true cost">
        <line x1="0" x2={W} y1={H} y2={H} stroke={AXIS} />
        {bins.map((b, i) => {
          const full = b.count - b.lower_bound_count;
          const hFull = (full / max) * (H - 12);
          const hLow = (b.lower_bound_count / max) * (H - 12);
          const x = i * slot + 1;
          const dim = hover !== null && hover !== i ? 0.45 : 0.85;
          return (
            <g key={b.lower_cents} tabIndex={0} onPointerEnter={() => setHover(i)} onPointerLeave={() => setHover(null)} onFocus={() => setHover(i)} onBlur={() => setHover(null)}>
              <rect x={i * slot} y={0} width={slot} height={H} fill="transparent" />
              {full > 0 && <path d={hLow > 0 ? `M${x},${H} V${H - hFull} H${x + bw} V${H} Z` : roundTop(x, H - hFull, bw, hFull, 3)} fill={HUE} opacity={dim} />}
              {hLow > 0 && <path d={roundTop(x, H - hFull - hLow - (full > 0 ? 2 : 0), bw, hLow, 3)} fill={LOWER} opacity={dim} />}
              {(bins.length <= 8 || i % 2 === 0) && (
                <text x={x + bw / 2} y={H + 12} textAnchor="middle" fontSize="8" fill={INK_MUTED} fontFamily="var(--font-mono)">
                  {k(b.lower_cents)}
                </text>
              )}
            </g>
          );
        })}
        {mx != null && mx >= 0 && mx <= W && (
          <g aria-hidden="true">
            <line x1={mx} x2={mx} y1={4} y2={H} stroke="#DDF8FF" strokeDasharray="3 3" strokeOpacity="0.6" />
            <text x={Math.min(W - 2, mx + 3)} y={10} fontSize="8" fill="#DDF8FF" fontFamily="var(--font-mono)" textAnchor={mx > W - 40 ? "end" : "start"}>
              median
            </text>
          </g>
        )}
      </svg>
      {hover !== null && bins[hover] && (
        <Tip
          x={((hover + 0.5) * slot * 100) / W}
          y={(((H - (bins[hover].count / max) * (H - 12)) / (H + 16)) * 100)}
          value={`${bins[hover].count} quotes${bins[hover].lower_bound_count ? ` · ${bins[hover].lower_bound_count}+` : ""}`}
          label={`${formatCents(bins[hover].lower_cents)}–${formatCents(bins[hover].upper_cents)}`}
        />
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Horizontal bars (response time, fee types, aircraft mix)            */
/* ------------------------------------------------------------------ */
function HBars({
  rows,
  format,
  max: maxIn,
}: {
  rows: { label: string; value: number; note?: string }[];
  format: (v: number) => string;
  max?: number;
}) {
  const max = maxIn ?? Math.max(1e-9, ...rows.map((r) => r.value));
  return (
    <ul className="space-y-2.5">
      {rows.map((r, i) => (
        <li
          key={`${r.label}-${i}`}
          tabIndex={0}
          title={`${r.label}: ${format(r.value)}${r.note ? ` (${r.note})` : ""}`}
          className="group grid grid-cols-[minmax(0,108px)_1fr_auto] items-center gap-3 rounded text-[11.5px] outline-none focus-visible:ring-1 focus-visible:ring-cyan/40"
        >
          <span className="truncate text-fg-muted group-hover:text-fg">{r.label}</span>
          <span className="h-2 overflow-hidden rounded-full bg-white/[0.05]">
            <span
              className="block h-full rounded-full transition-[width,opacity] duration-700 ease-out-expo group-hover:opacity-100"
              style={{ width: `${Math.max(2, (r.value / max) * 100)}%`, background: i === 0 ? EMPHASIS : HUE, opacity: i === 0 ? 1 : 0.8 }}
            />
          </span>
          <span className="tabular min-w-[42px] text-right font-mono text-[11px] text-fg">{format(r.value)}</span>
        </li>
      ))}
    </ul>
  );
}

/* ------------------------------------------------------------------ */
/* Funnel                                                              */
/* ------------------------------------------------------------------ */
function Funnel({ stages }: { stages: { label: string; value: number }[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const W = 300;
  const gutter = 84;
  const rowH = 22;
  const gap = 10;
  const H = stages.length * (rowH + gap) - gap;
  const max = Math.max(1, stages[0]?.value ?? 1);
  const barMax = W - gutter - 64;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label="Trip funnel">
      {stages.map((s, i) => {
        const w = Math.max(3, (s.value / max) * barMax);
        const y = i * (rowH + gap);
        const prev = i > 0 ? stages[i - 1].value : null;
        const conv = prev ? `${Math.round((s.value / prev) * 100)}%` : "";
        const last = i === stages.length - 1;
        return (
          <g key={s.label} tabIndex={0} onPointerEnter={() => setHover(i)} onPointerLeave={() => setHover(null)} onFocus={() => setHover(i)} onBlur={() => setHover(null)}>
            <title>{`${s.label}: ${s.value} trips${conv ? ` (${conv} of previous)` : ""}`}</title>
            <rect x={0} y={y} width={W} height={rowH} fill="transparent" />
            <text x={0} y={y + rowH / 2 + 3.5} fontSize="10" fill={INK_MUTED}>
              {s.label}
            </text>
            <rect x={gutter} y={y} width={w} height={rowH} rx={4} fill={last ? EMPHASIS : HUE} opacity={hover === null || hover === i ? (last ? 1 : 0.85) : 0.4} />
            <text x={gutter + w + 6} y={y + rowH / 2 + 3.5} fontSize="10" fill="#f5f7fa" fontFamily="var(--font-mono)">
              {s.value}
              {conv && <tspan fill={INK_MUTED}> · {conv}</tspan>}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
