"use client";

import { useRef, useState } from "react";
import { useInView } from "motion/react";
import { FileText } from "lucide-react";
import { SectionHeader } from "@/components/ui/section-header";
import { Reveal, RevealGroup, RevealItem } from "@/components/ui/reveal";
import { AnimatedNumber } from "@/components/ui/animated-number";
import { ConfidenceBadge } from "@/components/ui/confidence-badge";
import { WATERFALL, WATERFALL_META, WATERFALL_TOTAL } from "@/lib/demo-data";
import { cn, formatSigned, formatUSD } from "@/lib/utils";

const SEGMENT_COLORS = ["#5B8CFF", "#59D9FF", "#8EE7FF", "#DDF8FF", "#F6B95B"];

export function TrueCost() {
  const [active, setActive] = useState<number | null>(null);
  const barRef = useRef<HTMLDivElement>(null);
  const barIn = useInView(barRef, { once: true, amount: 0.8 });
  const added = WATERFALL.slice(1).filter((l) => l.amount !== null);
  const base = WATERFALL[0].amount ?? 0;

  return (
    <section id="true-cost" className="container-x py-24 sm:py-32">
      <div className="grid gap-12 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:items-center lg:gap-16">
        <div>
          <SectionHeader
            eyebrow="True cost"
            title="Headline price isn't the final price."
            lead="JetStream rebuilds every quote line by line from its source documents, then normalizes the result so two operators' totals finally mean the same thing."
          />
          <Reveal delay={0.1} className="mt-8 space-y-3 text-[13.5px] text-fg-muted">
            <p className="flex items-start gap-3">
              <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-cyan" aria-hidden="true" />
              Every line links to the page it came from.
            </p>
            <p className="flex items-start gap-3">
              <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-cyan" aria-hidden="true" />
              Included items stay visible, so &ldquo;included&rdquo; is a fact, not an assumption.
            </p>
            <p className="flex items-start gap-3">
              <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-cyan" aria-hidden="true" />
              Hover or tap a line to see its source and confidence.
            </p>
          </Reveal>
        </div>

        <Reveal className="surface-card edge-light p-5 sm:p-6">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="eyebrow text-[10px]">
              Demo quote <span className="text-fg-dim">·</span> {WATERFALL_META.flightId}{" "}
              <span className="text-fg-dim">·</span>{" "}
              <span className="normal-case tracking-normal text-fg-muted">{WATERFALL_META.route}</span>
            </p>
            <p className="inline-flex items-center gap-1.5 font-mono text-[10.5px] text-fg-dim">
              <FileText className="h-3 w-3" aria-hidden="true" /> {WATERFALL_META.file}
            </p>
          </div>

          <RevealGroup as="ul" className="mt-4 -mx-2" staggerChildren={0.09}>
            {WATERFALL.map((line, i) => {
              const isActive = active === i;
              return (
                <RevealItem as="li" key={line.label} className={cn(i === 1 && "mt-1 border-t border-line pt-1")}>
                  <button
                    type="button"
                    onPointerEnter={() => setActive(i)}
                    onPointerLeave={() => setActive((a) => (a === i ? null : a))}
                    onFocus={() => setActive(i)}
                    onBlur={() => setActive((a) => (a === i ? null : a))}
                    onClick={() => setActive((a) => (a === i ? null : i))}
                    aria-expanded={isActive}
                    className={cn(
                      "grid w-full grid-cols-[1fr_auto] items-center gap-3 rounded-lg px-3 py-2 text-left transition-colors duration-200",
                      isActive ? "bg-white/[0.045]" : "hover:bg-white/[0.03]",
                    )}
                  >
                    <span className="min-w-0">
                      <span className={cn("block text-[14px]", i === 0 ? "font-medium text-fg" : "text-fg-muted")}>
                        {line.label}
                      </span>
                      <span
                        className={cn(
                          "block h-4 truncate font-mono text-[10.5px] text-fg-dim transition-opacity duration-200",
                          isActive ? "opacity-100" : "opacity-0",
                        )}
                        aria-hidden={!isActive}
                      >
                        Source: {line.source}
                        {line.page ? ` · page ${line.page}` : ""} · Confidence {line.confidence}%
                      </span>
                    </span>
                    <span className="flex items-center gap-3">
                      <span
                        className={cn(
                          "transition-opacity duration-200",
                          isActive ? "opacity-100" : "opacity-0",
                        )}
                        aria-hidden={!isActive}
                      >
                        <ConfidenceBadge value={line.confidence} />
                      </span>
                      <span
                        className={cn(
                          "tabular font-mono text-[14px]",
                          line.amount === null ? "text-fg-dim" : i === 0 ? "text-fg" : "text-fg",
                        )}
                      >
                        {line.amount === null
                          ? "Included"
                          : i === 0
                            ? formatUSD(line.amount)
                            : formatSigned(line.amount)}
                      </span>
                    </span>
                  </button>
                </RevealItem>
              );
            })}
          </RevealGroup>

          <div className="mt-3 border-t border-line pt-4">
            <div className="flex items-end justify-between gap-4">
              <p className="eyebrow text-[10px]">True estimated cost</p>
              <p className="text-[30px] font-semibold leading-none tracking-[-0.03em] text-fg sm:text-[34px]">
                <AnimatedNumber value={WATERFALL_TOTAL} from={base} duration={1.4} />
              </p>
            </div>

            {/* proportion bar */}
            <div ref={barRef} className="mt-4 flex h-2 w-full gap-px overflow-hidden rounded-full bg-white/[0.05]">
              <div
                className="h-full origin-left rounded-l-full bg-white/[0.16] transition-transform duration-1000 ease-out-expo"
                style={{ width: `${(base / WATERFALL_TOTAL) * 100}%`, transform: barIn ? "scaleX(1)" : "scaleX(0)" }}
              />
              {added.map((l, i) => (
                <div
                  key={l.label}
                  className="h-full origin-left transition-transform duration-700 ease-out-expo"
                  style={{
                    width: `${((l.amount ?? 0) / WATERFALL_TOTAL) * 100}%`,
                    background: SEGMENT_COLORS[i % SEGMENT_COLORS.length],
                    transform: barIn ? "scaleX(1)" : "scaleX(0)",
                    transitionDelay: `${0.6 + i * 0.12}s`,
                  }}
                />
              ))}
            </div>
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 font-mono text-[10px] text-fg-dim">
              <span>Headline {Math.round((base / WATERFALL_TOTAL) * 100)}%</span>
              <span className="text-fg-muted">
                Added charges {Math.round(((WATERFALL_TOTAL - base) / WATERFALL_TOTAL) * 100)}% ·{" "}
                {formatUSD(WATERFALL_TOTAL - base)}
              </span>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
