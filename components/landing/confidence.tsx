"use client";

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { AlertTriangle, Check, Loader2, MessageSquare } from "lucide-react";
import { SectionHeader } from "@/components/ui/section-header";
import { Reveal } from "@/components/ui/reveal";
import { ConfidenceBadge } from "@/components/ui/confidence-badge";
import { GlowButton } from "@/components/ui/glow-button";
import { EASE_OUT_EXPO } from "@/lib/animations";
import { cn } from "@/lib/utils";

type State = "idle" | "working" | "verified" | "accepted";

export function Confidence() {
  const [state, setState] = useState<State>("idle");
  const timer = useRef<number | null>(null);
  const done = state === "verified" || state === "accepted";

  const act = (next: "verified" | "accepted") => {
    setState("working");
    timer.current = window.setTimeout(() => setState(next), 800);
  };
  useEffect(() => () => {
    if (timer.current) window.clearTimeout(timer.current);
  }, []);

  return (
    <section id="verification" className="container-x py-24 sm:py-32">
      <div className="grid gap-12 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:items-center lg:gap-16">
        <div>
          <SectionHeader
            eyebrow="Human in the loop"
            title="AI handles the work. You keep the final say."
            lead="Every figure carries a confidence score. Anything below your threshold waits for a broker before it reaches a client, with the source right beside it."
          />
          <Reveal delay={0.1} className="mt-8 grid grid-cols-1 gap-2.5 sm:grid-cols-3 sm:gap-3">
            {[
              ["Field-level", "scores on every value"],
              ["One click", "to verify or accept"],
              ["Source", "snippet beside each figure"],
            ].map(([a, b]) => (
              <div
                key={a}
                className="flex items-baseline gap-2 rounded-xl border border-line bg-white/[0.02] px-3.5 py-3 sm:block"
              >
                <p className="text-[13.5px] font-medium text-fg">{a}</p>
                <p className="text-[12px] leading-snug text-fg-muted sm:mt-0.5">{b}</p>
              </div>
            ))}
          </Reveal>
        </div>

        <Reveal>
          <div
            className={cn(
              "surface-card edge-light relative p-5 transition-[border-color,box-shadow] duration-700 ease-out-expo sm:p-6",
              done && "border-green/30 shadow-[0_0_0_1px_rgba(101,211,155,0.15),0_30px_80px_-40px_rgba(101,211,155,0.35)]",
            )}
            aria-live="polite"
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="eyebrow text-[10px]">
                Field review <span className="text-fg-dim">·</span>{" "}
                <span className="normal-case tracking-normal text-fg-muted">revised-quote.pdf · SMS thread</span>
              </p>
              <p className="font-mono text-[10.5px] text-fg-dim">
                <span className="tabular text-fg-muted">{done ? 2 : 3}</span> of 31 fields need review
              </p>
            </div>

            <p className="mt-5 text-[13.5px] text-fg-muted">Fuel surcharge</p>
            <div className="mt-1 flex flex-wrap items-end gap-3">
              <p className="tabular text-[38px] font-semibold leading-none tracking-[-0.03em] text-fg">$850</p>
              <div className="pb-1">
                <ConfidenceBadge value={done ? 100 : 63} verified={done} label="confidence" size="md" />
              </div>
            </div>

            <div className="mt-4 min-h-[22px]">
              <AnimatePresence mode="wait" initial={false}>
                {done ? (
                  <motion.p
                    key="done"
                    initial={{ opacity: 0, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -4 }}
                    transition={{ duration: 0.25, ease: EASE_OUT_EXPO }}
                    className="inline-flex items-center gap-2 text-[13px] text-green"
                  >
                    <Check className="h-3.5 w-3.5" strokeWidth={2.5} aria-hidden="true" />
                    {state === "verified" ? "Verified by broker" : "Accepted by broker"} · locked for the proposal
                  </motion.p>
                ) : (
                  <motion.p
                    key="idle"
                    initial={{ opacity: 0, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -4 }}
                    transition={{ duration: 0.25, ease: EASE_OUT_EXPO }}
                    className="inline-flex items-center gap-2 text-[13px] text-amber"
                  >
                    <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
                    Possible ambiguity detected. The operator says fuel “may be extra”.
                  </motion.p>
                )}
              </AnimatePresence>
            </div>

            <blockquote className="mt-4 rounded-lg border border-line bg-black/25 p-3.5">
              <p className="flex items-center gap-1.5 font-mono text-[10px] tracking-[0.12em] text-fg-dim">
                <MessageSquare className="h-3 w-3" aria-hidden="true" /> SOURCE · SMS · OCT 3 · 11:48
              </p>
              <p className="mt-2 font-mono text-[12px] leading-relaxed text-fg-muted">
                “…quote is 38,900 all in, crew overnight 700 extra.{" "}
                <mark className={cn("rounded-sm px-0.5 transition-colors duration-500", done ? "bg-green/20 text-green" : "bg-amber/20 text-amber")}>
                  fuel may be extra, est. 850
                </mark>{" "}
                depending on uplift at KOPF…”
              </p>
            </blockquote>

            <div className="mt-5 flex flex-wrap items-center gap-2">
              {done ? (
                <GlowButton variant="ghost" size="sm" onClick={() => setState("idle")}>
                  Reset demo
                </GlowButton>
              ) : (
                <>
                  <GlowButton
                    size="sm"
                    onClick={() => act("verified")}
                    disabled={state === "working"}
                    icon={
                      state === "working" ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Check className="h-3.5 w-3.5" strokeWidth={2.5} />
                      )
                    }
                  >
                    {state === "working" ? "Verifying" : "Verify"}
                  </GlowButton>
                  <GlowButton variant="secondary" size="sm" onClick={() => act("accepted")} disabled={state === "working"}>
                    Accept
                  </GlowButton>
                </>
              )}
              <span className="ml-auto font-mono text-[10px] tracking-[0.12em] text-fg-dim">DEMO INTERACTION</span>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
