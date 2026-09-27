"use client";

import { useRef } from "react";
import { motion, useInView } from "motion/react";
import { AlertTriangle, ArrowRight, FileText, Sparkles } from "lucide-react";
import { SectionHeader } from "@/components/ui/section-header";
import { RevealGroup, RevealItem } from "@/components/ui/reveal";
import { ConfidenceBadge } from "@/components/ui/confidence-badge";
import { enter } from "@/lib/animations";
import { cn } from "@/lib/utils";

/* ------------------------------------------------------------------ */
/* Module shell                                                        */
/* ------------------------------------------------------------------ */

function Module({
  verb,
  title,
  body,
  className,
  children,
}: {
  verb: string;
  title: string;
  body: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <RevealItem as="article" className={cn("surface-card flex flex-col p-5 sm:p-6", className)}>
      <div className="flex-1">{children}</div>
      <div className="mt-6">
        <p className="eyebrow text-[10px] text-cyan/80">{verb}</p>
        <h3 className="mt-2 text-[17px] font-semibold tracking-[-0.02em] text-fg">{title}</h3>
        <p className="mt-1.5 text-[13.5px] leading-relaxed text-fg-muted">{body}</p>
      </div>
    </RevealItem>
  );
}

/* ------------------------------------------------------------------ */
/* 1 · Read every quote: raw → fields → object                         */
/* ------------------------------------------------------------------ */

const RAW_LINES: { text: string; token?: string }[] = [
  { text: "Thanks for the request, please see below" },
  { text: "Aircraft: ", token: "Citation Latitude" },
  { text: "Trip total ", token: "$41,800" },
  { text: "incl. std. handling. ", token: "Positioning $1,200" },
  { text: "Catering included, fuel surcharge ", token: "$1,400" },
  { text: "Let us know if you'd like to hold." },
];

const FIELDS = [
  ["aircraft", "Citation Latitude"],
  ["headline_price", "41,800"],
  ["positioning", "1,200"],
  ["fuel_surcharge", "1,400"],
  ["catering", "included"],
];

function ReadVisual() {
  const ref = useRef<HTMLDivElement>(null);
  const active = useInView(ref, { once: true, amount: 0.5 });
  return (
    <div
      ref={ref}
      className="grid grid-cols-1 items-center gap-3 sm:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] sm:gap-4"
    >
      {/* raw document */}
      <div className="min-w-0 rounded-lg border border-line bg-white/[0.03] p-3">
        <div className="mb-2 flex items-center gap-1.5 font-mono text-[9.5px] text-fg-dim">
          <FileText className="h-3 w-3" aria-hidden="true" /> atlas_quote_01.pdf
        </div>
        <ul className="space-y-1.5 text-[10px] leading-4 text-fg-dim">
          {RAW_LINES.map((l, i) => (
            <li key={i} className="truncate">
              {l.text}
              {l.token && (
                <span
                  style={{ transitionDelay: active ? `${0.3 + i * 0.18}s` : "0s" }}
                  className={cn(
                    "rounded-sm px-0.5 transition-[background-color,color] duration-500",
                    active ? "bg-cyan/20 text-ice" : "bg-transparent text-fg-dim",
                  )}
                >
                  {l.token}
                </span>
              )}
            </li>
          ))}
        </ul>
      </div>

      <div className="flex items-center justify-center gap-1 text-fg-dim sm:flex-col">
        <Sparkles className="h-3.5 w-3.5 text-cyan" aria-hidden="true" />
        <ArrowRight className="h-3.5 w-3.5 rotate-90 sm:rotate-0" aria-hidden="true" />
      </div>

      {/* clean object */}
      <div className="min-w-0 rounded-lg border border-cyan/20 bg-[#0a1219] p-3 font-mono text-[10px] leading-[1.7]">
        <span className="text-fg-dim">{"{"}</span>
        <ul>
          {FIELDS.map(([k, v], i) => (
            <motion.li
              key={k}
              initial={{ opacity: 0, x: 6 }}
              animate={active ? { opacity: 1, x: 0 } : {}}
              transition={{ ...enter, delay: 0.9 + i * 0.16 }}
              className="truncate pl-3"
            >
              <span className="text-cyan">{k}</span>
              <span className="text-fg-dim">: </span>
              <span className="text-ice">{/^[\d,]+$/.test(v) ? v : `"${v}"`}</span>
              {i < FIELDS.length - 1 && <span className="text-fg-dim">,</span>}
            </motion.li>
          ))}
        </ul>
        <span className="text-fg-dim">{"}"}</span>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* 2 · True cost: fee vocabulary                                       */
/* ------------------------------------------------------------------ */

const FEE_TYPES = [
  ["Hourly rate", "$6,200"],
  ["Positioning", "$1,200"],
  ["Ramp / handling", "$420"],
  ["Crew", "$700"],
  ["Fuel", "$1,400"],
  ["Catering", "Incl."],
  ["Overnight", "$550"],
  ["International", "$350"],
];

function CostVisual() {
  return (
    <div className="flex flex-wrap gap-1.5">
      {FEE_TYPES.map(([k, v], i) => (
        <span
          key={k}
          className={cn(
            "inline-flex items-center gap-2 rounded-md border px-2 py-1 text-[11px]",
            i === 0 ? "border-line-strong bg-white/[0.05] text-fg" : "border-line bg-white/[0.02] text-fg-muted",
          )}
        >
          {k}
          <span className="tabular font-mono text-[10.5px] text-fg-dim">{v}</span>
        </span>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* 3 · Hidden fee detection                                            */
/* ------------------------------------------------------------------ */

function WarningVisual() {
  return (
    <div className="rounded-lg border border-amber/30 bg-amber/[0.06] p-3.5">
      <p className="inline-flex items-center gap-1.5 font-mono text-[10px] tracking-[0.14em] text-amber">
        <AlertTriangle className="h-3 w-3" aria-hidden="true" /> POTENTIAL MISSING CHARGE
      </p>
      <div className="mt-3 grid grid-cols-2 gap-3 text-[11.5px]">
        <div>
          <p className="text-fg-dim">Quote includes</p>
          <p className="mt-1 text-fg">Base price</p>
        </div>
        <div>
          <p className="text-fg-dim">JetStream detected</p>
          <ul className="mt-1 space-y-0.5 text-fg">
            <li>Crew overnight</li>
            <li>Ramp fee</li>
            <li>Positioning</li>
          </ul>
        </div>
      </div>
      <a
        href="#verification"
        className="mt-3.5 inline-flex h-8 items-center rounded-md border border-amber/40 px-3 text-[11.5px] font-medium text-amber transition-colors hover:bg-amber/10"
      >
        Review
      </a>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* 4 · Confidence + human verification                                 */
/* ------------------------------------------------------------------ */

const CONF_FIELDS: [string, number][] = [
  ["Aircraft type", 99],
  ["Hourly rate", 98],
  ["Fuel estimate", 87],
  ["Ramp fee", 61],
];

function ConfidenceVisual() {
  const ref = useRef<HTMLUListElement>(null);
  const active = useInView(ref, { once: true, amount: 0.5 });
  return (
    <div>
      <ul ref={ref} className="space-y-2">
        {CONF_FIELDS.map(([label, v], i) => (
          <li key={label} className="grid grid-cols-[1fr_auto] items-center gap-3 text-[12px]">
            <div>
              <div className="flex items-center justify-between">
                <span className={cn(v < 75 ? "text-amber" : "text-fg-muted")}>{label}</span>
              </div>
              <div className="mt-1 h-1 overflow-hidden rounded-full bg-white/[0.06]">
                <div
                  style={{ width: `${v}%`, transitionDelay: `${0.2 + i * 0.12}s`, transform: active ? "scaleX(1)" : "scaleX(0)" }}
                  className={cn(
                    "h-full origin-left rounded-full transition-transform duration-700 ease-out-expo",
                    v < 75 ? "bg-amber" : "bg-[linear-gradient(90deg,#5B8CFF,#59D9FF)]",
                  )}
                />
              </div>
            </div>
            <ConfidenceBadge value={v} />
          </li>
        ))}
      </ul>
      <a
        href="#verification"
        className="mt-4 inline-flex h-8 items-center rounded-md border border-line-strong px-3 text-[11.5px] font-medium text-fg transition-colors hover:bg-white/[0.05]"
      >
        Review field
      </a>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* 5 · Client-ready proposal                                           */
/* ------------------------------------------------------------------ */

function ProposalVisual() {
  return (
    <div className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-3">
      <div className="min-w-0 overflow-hidden rounded-lg border border-line bg-white/[0.03] p-2.5 font-mono text-[9.5px] leading-4 text-fg-dim">
        <p className="text-fg-muted">broker · q-atlas</p>
        <p>base 41800 · pos 1200</p>
        <p>ramp 420 · fuel 1400</p>
        <p>conf 0.97 · src p.1–2</p>
      </div>
      <ArrowRight className="h-3.5 w-3.5 text-fg-dim" aria-hidden="true" />
      <div className="min-w-0 rounded-lg border border-line bg-[linear-gradient(180deg,rgba(255,255,255,0.06),rgba(255,255,255,0.02))] p-3">
        <p className="text-[12px] font-medium text-fg">Citation Latitude</p>
        <p className="mt-1 text-[11px] text-fg-muted">
          $44,820 <span className="text-fg-dim">est. total</span>
        </p>
        <p className="mt-1.5 text-[10.5px] text-fg-dim">7 passengers · Wi-Fi · 2h 58m</p>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */

export function Features() {
  return (
    <section className="container-x py-24 sm:py-32">
      <SectionHeader
        eyebrow="Core capabilities"
        title="Every format. One structured view."
        lead="Five things JetStream does to every quote before a broker sees it."
      />
      <RevealGroup className="mt-12 grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-6" staggerChildren={0.08}>
        <Module
          verb="Read"
          title="Read every quote"
          body="PDFs, emails and messages become the same structured fields, with every value traced back to its source."
          className="lg:col-span-4"
        >
          <ReadVisual />
        </Module>
        <Module
          verb="Normalize"
          title="Know the price that actually matters"
          body="Hourly rates, positioning, handling, crew, fuel, catering, overnight and international fees are reconciled into one total."
          className="lg:col-span-2"
        >
          <CostVisual />
        </Module>
        <Module
          verb="Detect"
          title="Catch what the quote left out"
          body="Charges that are standard for a route but absent from a quote are flagged before they surprise a client."
          className="lg:col-span-2"
        >
          <WarningVisual />
        </Module>
        <Module
          verb="Verify"
          title="Field-level confidence"
          body="Every extracted figure carries a score. Anything uncertain waits for a broker's one-click review."
          className="lg:col-span-2"
        >
          <ConfidenceVisual />
        </Module>
        <Module
          verb="Deliver"
          title="Client-ready proposal"
          body="Internal broker data becomes a clean, comparable proposal without a single copy-paste."
          className="lg:col-span-2"
        >
          <ProposalVisual />
        </Module>
      </RevealGroup>
    </section>
  );
}
