"use client";

import { motion } from "motion/react";
import { ArrowDown, ArrowRight } from "lucide-react";
import { GlowButton } from "@/components/ui/glow-button";
import { QuoteDemo } from "@/components/landing/quote-demo";
import { TelemetryNetwork } from "@/components/landing/telemetry-network";
import { CONTACT_HREF } from "@/lib/demo-data";
import { fadeUp, scaleIn, stagger, wordReveal } from "@/lib/animations";
import { cn } from "@/lib/utils";

const HEADLINE: { text: string; accent?: boolean }[] = [
  { text: "Turn" },
  { text: "every" },
  { text: "charter" },
  { text: "quote" },
  { text: "into" },
  { text: "a" },
  { text: "clear", accent: true },
  { text: "decision.", accent: true },
];

export function Hero() {
  return (
    <section id="top" className="relative overflow-hidden pb-16 pt-[128px] sm:pb-24 sm:pt-[156px]">
      {/* telemetry network behind the hero */}
      <div
        aria-hidden="true"
        className="absolute inset-x-0 top-0 h-[900px] [mask-image:radial-gradient(ellipse_75%_65%_at_50%_32%,#000_25%,transparent_78%)]"
      >
        <TelemetryNetwork className="absolute inset-0" />
      </div>

      {/* hero glow */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute left-1/2 top-[-12%] h-[560px] w-[1100px] -translate-x-1/2 rounded-full bg-[radial-gradient(ellipse_at_center,rgba(91,140,255,0.22)_0%,rgba(89,217,255,0.08)_38%,transparent_70%)] blur-2xl"
      />

      <motion.div
        variants={stagger(0.09, 0.12)}
        initial="hidden"
        animate="show"
        className="container-x relative z-10 flex flex-col items-center text-center"
      >
        <motion.h1
          variants={stagger(0.055, 0.05)}
          className="max-w-[13.5ch] text-[2.75rem] font-semibold leading-[1.02] tracking-[-0.04em] sm:text-[3.7rem] lg:text-[4.75rem]"
        >
          {HEADLINE.map((w, i) => (
            <span key={i}>
              <motion.span
                variants={wordReveal}
                className={cn(
                  "inline-block will-change-transform",
                  w.accent ? "text-gradient-accent" : "text-gradient-ice",
                )}
              >
                {w.text}
              </motion.span>
              {i < HEADLINE.length - 1 ? " " : ""}
            </span>
          ))}
        </motion.h1>

        <motion.p
          variants={fadeUp}
          className="mt-6 max-w-[42rem] text-base leading-relaxed text-fg-muted sm:text-lg"
        >
          JetStream reads the PDFs, emails and messages your operators send back, extracting pricing,
          aircraft details, hidden fees and logistics into one clean, comparable view.
        </motion.p>

        <motion.div variants={fadeUp} className="mt-9 flex flex-col items-center gap-3 sm:flex-row">
          <GlowButton size="lg" href={CONTACT_HREF} icon={<ArrowRight className="h-4 w-4" />}>
            Request early access
          </GlowButton>
          <GlowButton
            size="lg"
            variant="secondary"
            href="#how-it-works"
            icon={<ArrowDown className="h-4 w-4" />}
          >
            See how it works
          </GlowButton>
        </motion.div>

        <motion.p variants={fadeUp} className="mt-5 font-mono text-[11px] tracking-[0.14em] text-fg-dim">
          WORKS WITH THE QUOTES YOU ALREADY RECEIVE
        </motion.p>
      </motion.div>

      <motion.div
        variants={scaleIn}
        custom={0.55}
        initial="hidden"
        animate="show"
        className="container-wide relative z-10 mt-14 sm:mt-20"
      >
        <QuoteDemo />
      </motion.div>
    </section>
  );
}
