"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { ArrowRight, Clock, Star, Users, Wifi } from "lucide-react";
import { SectionHeader } from "@/components/ui/section-header";
import { Reveal } from "@/components/ui/reveal";
import { ConfidenceBadge } from "@/components/ui/confidence-badge";
import { PROPOSAL_OPTIONS, QUOTES, REQUEST } from "@/lib/demo-data";
import { EASE_OUT_EXPO } from "@/lib/animations";
import { cn, formatUSD } from "@/lib/utils";

type View = "client" | "broker";

function ClientView() {
  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2 font-mono text-[10.5px] tracking-[0.12em] text-fg-dim">
        <span>PREPARED FOR · PRIVATE CLIENT</span>
        <span>PREPARED BY · YOUR BROKERAGE</span>
      </div>
      <div className="mt-10 text-center">
        <p className="eyebrow">Your private charter options</p>
        <h3 className="mt-4 text-[30px] font-semibold tracking-[-0.03em] text-fg sm:text-[38px]">
          {REQUEST.from} <span className="text-fg-dim">→</span> {REQUEST.to}
        </h3>
        <p className="mt-2 text-[15px] text-fg-muted">
          {REQUEST.dateLong} · {REQUEST.pax} passengers
        </p>
      </div>

      <ul className="mt-10 grid gap-4 md:grid-cols-3">
        {PROPOSAL_OPTIONS.map((o, i) => (
          <motion.li
            key={o.id}
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease: EASE_OUT_EXPO, delay: 0.1 + i * 0.1 }}
            className={cn(
              "relative flex flex-col rounded-2xl border p-6",
              o.recommended
                ? "border-amber/40 bg-[linear-gradient(180deg,rgba(246,185,91,0.08),rgba(255,255,255,0.02))] shadow-[0_0_0_1px_rgba(246,185,91,0.12),0_30px_60px_-30px_rgba(246,185,91,0.35)]"
                : "border-line bg-white/[0.02]",
            )}
          >
            {o.recommended && (
              <span className="absolute -top-3 left-6 inline-flex items-center gap-1.5 rounded-full border border-amber/40 bg-[#1c1710] px-2.5 py-1 font-mono text-[10px] tracking-[0.14em] text-amber">
                <Star className="h-3 w-3 fill-current" aria-hidden="true" /> RECOMMENDED
              </span>
            )}
            <p className="text-[20px] font-semibold tracking-[-0.02em] text-fg">{o.aircraft}</p>
            <p className="mt-0.5 text-[12.5px] text-fg-dim">{o.category}</p>
            <p className="tabular mt-6 text-[28px] font-semibold leading-none tracking-[-0.03em] text-fg">
              {formatUSD(o.total)}
            </p>
            <p className="mt-1.5 text-[12.5px] text-fg-muted">estimated total, all known charges included</p>
            <ul className="mt-6 space-y-2 border-t border-line pt-5 text-[13px] text-fg-muted">
              <li className="flex items-center gap-2.5">
                <Users className="h-3.5 w-3.5 text-fg-dim" aria-hidden="true" /> {o.seats} seats · {REQUEST.pax} passengers
              </li>
              <li className="flex items-center gap-2.5">
                <Wifi className="h-3.5 w-3.5 text-fg-dim" aria-hidden="true" /> {o.wifi ? "Wi-Fi on board" : "No Wi-Fi"}
              </li>
              <li className="flex items-center gap-2.5">
                <Clock className="h-3.5 w-3.5 text-fg-dim" aria-hidden="true" /> {o.flightTime} flight time
              </li>
            </ul>
            <a
              href="#proposal"
              className="group mt-6 inline-flex items-center gap-1.5 text-[13px] font-medium text-fg transition-colors hover:text-cyan"
            >
              View aircraft
              <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" aria-hidden="true" />
            </a>
          </motion.li>
        ))}
      </ul>
      <p className="mt-8 text-center text-[12px] text-fg-dim">
        Estimates include every charge stated in or detected from operator quotes. Final pricing is confirmed at
        booking.
      </p>
    </div>
  );
}

function BrokerView() {
  return (
    <div className="overflow-x-auto">
      <div className="flex items-center justify-between font-mono text-[10.5px] tracking-[0.12em] text-fg-dim">
        <span>WORKSPACE · {REQUEST.id} · 4 QUOTES</span>
        <span>SOURCES VISIBLE · CONFIDENCE VISIBLE</span>
      </div>
      <table className="mt-6 w-full min-w-[720px] border-separate border-spacing-0 text-[12.5px]">
        <thead>
          <tr className="font-mono text-[10px] uppercase tracking-[0.14em] text-fg-dim">
            {["Operator", "Aircraft", "Headline", "Added charges", "True cost", "Confidence", "Source"].map((h, i) => (
              <th
                key={h}
                className={cn(
                  "border-b border-line pb-2 pr-4 font-normal last:pr-0",
                  i >= 2 && i <= 4 ? "text-right" : "text-left",
                )}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {QUOTES.map((q) => (
            <tr key={q.id} className={cn(q.warning && "text-amber")}>
              <td className="border-b border-line py-3 pr-3 text-fg">{q.operator}</td>
              <td className="border-b border-line py-3 pr-3 text-fg-muted">{q.aircraft}</td>
              <td className="tabular border-b border-line py-3 pr-3 text-right font-mono text-fg-muted">
                {formatUSD(q.headline)}
              </td>
              <td className="tabular border-b border-line py-3 pr-3 text-right font-mono text-fg-muted">
                {formatUSD(q.trueCost - q.headline)}
                {q.warning && "+"}
              </td>
              <td className="tabular border-b border-line py-3 pr-4 text-right font-mono text-fg">
                {formatUSD(q.trueCost)}
              </td>
              <td className="border-b border-line py-3 pr-4">
                <ConfidenceBadge value={q.warning ? 61 : q.finalFit} />
              </td>
              <td className="border-b border-line py-3 font-mono text-[11px] text-fg-dim">{q.sourceFile}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-4 text-[12px] text-fg-dim">
        Amber rows carry a flagged field and are held out of the client proposal until a broker reviews them.
      </p>
    </div>
  );
}

export function ProposalDemo() {
  const [view, setView] = useState<View>("client");

  return (
    <section id="proposal" className="container-x py-24 sm:py-32">
      <SectionHeader
        align="center"
        eyebrow="Client-ready"
        title="From broker workspace to client proposal in one action."
        lead="The same verified data, two audiences. Brokers see sources and confidence. Clients see a decision."
      />

      <Reveal className="mt-10">
        <div className="flex justify-center">
          <div role="tablist" aria-label="Proposal view" className="glass relative inline-flex rounded-full p-1">
            {(["client", "broker"] as View[]).map((v) => {
              const selected = view === v;
              return (
                <button
                  key={v}
                  role="tab"
                  type="button"
                  aria-selected={selected}
                  aria-controls={`proposal-panel-${v}`}
                  id={`proposal-tab-${v}`}
                  onClick={() => setView(v)}
                  className={cn(
                    "relative z-10 h-9 rounded-full px-4 text-[13px] font-medium transition-colors duration-200",
                    selected ? "text-bg-deep" : "text-fg-muted hover:text-fg",
                  )}
                >
                  {selected && (
                    <motion.span
                      layoutId="proposal-tab-bg"
                      transition={{ type: "spring", stiffness: 420, damping: 34 }}
                      className="absolute inset-0 -z-10 rounded-full bg-[linear-gradient(135deg,#f2fdff,#9fe9ff_45%,#5b8cff)]"
                    />
                  )}
                  {v === "client" ? "Client view" : "Broker view"}
                </button>
              );
            })}
          </div>
        </div>

        <div className="relative mt-8 overflow-hidden rounded-3xl border border-line bg-[linear-gradient(180deg,#111925_0%,#0b0f16_100%)] p-6 shadow-shell sm:p-10 lg:p-12">
          <div
            aria-hidden="true"
            className="pointer-events-none absolute -top-40 left-1/2 h-80 w-[720px] -translate-x-1/2 rounded-full bg-[radial-gradient(circle,rgba(91,140,255,0.16),transparent_65%)] blur-2xl"
          />
          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={view}
              id={`proposal-panel-${view}`}
              role="tabpanel"
              aria-labelledby={`proposal-tab-${view}`}
              initial={{ opacity: 0, y: 10, filter: "blur(4px)" }}
              animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
              exit={{ opacity: 0, y: -8, filter: "blur(4px)" }}
              transition={{ duration: 0.35, ease: EASE_OUT_EXPO }}
              className="relative"
            >
              {view === "client" ? <ClientView /> : <BrokerView />}
            </motion.div>
          </AnimatePresence>
        </div>
      </Reveal>
    </section>
  );
}
