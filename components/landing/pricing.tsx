import { ArrowRight, Check } from "lucide-react";
import { SectionHeader } from "@/components/ui/section-header";
import { Reveal } from "@/components/ui/reveal";
import { GlowButton } from "@/components/ui/glow-button";
import { CONTACT_HREF } from "@/lib/demo-data";

const INCLUDED = [
  "Per-broker seats, sized to your desk",
  "Hands-on setup with your real operator quotes",
  "Human verification on every low-confidence field",
  "Pilot pricing shared during onboarding",
];

export function Pricing() {
  return (
    <section id="pricing" className="container-x py-24 sm:py-32">
      <SectionHeader
        align="center"
        eyebrow="Pricing"
        title="Early access for brokerages that live in their inbox."
        lead="Built for boutique and growing charter brokerages."
      />
      <Reveal className="mx-auto mt-12 max-w-2xl">
        <div className="glass-strong edge-light relative overflow-hidden rounded-3xl p-8 shadow-shell sm:p-10">
          <div
            aria-hidden="true"
            className="pointer-events-none absolute -right-24 -top-24 h-64 w-64 rounded-full bg-[radial-gradient(circle,rgba(89,217,255,0.18),transparent_65%)] blur-2xl"
          />
          <div className="relative grid gap-8 sm:grid-cols-[1fr_auto] sm:items-start">
            <div>
              <p className="eyebrow text-cyan/80">Early access</p>
              <p className="mt-3 text-[34px] font-semibold leading-none tracking-[-0.03em] text-fg sm:text-[40px]">
                Talk to us
              </p>
              <p className="mt-3 max-w-md text-[14px] leading-relaxed text-fg-muted">
                We onboard a small number of brokerages at a time, so every workspace gets set up on the quotes it
                actually receives.
              </p>
            </div>
            <GlowButton size="lg" href={CONTACT_HREF} icon={<ArrowRight className="h-4 w-4" />}>
              Request access
            </GlowButton>
          </div>
          <ul className="relative mt-8 grid gap-2.5 border-t border-line pt-6 sm:grid-cols-2">
            {INCLUDED.map((item) => (
              <li key={item} className="flex items-start gap-2.5 text-[13.5px] text-fg-muted">
                <span className="mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded-full bg-cyan/15 text-cyan">
                  <Check className="h-2.5 w-2.5" strokeWidth={3} aria-hidden="true" />
                </span>
                {item}
              </li>
            ))}
          </ul>
          <p className="relative mt-6 font-mono text-[10.5px] tracking-[0.1em] text-fg-dim">
            PILOT PRICING · ILLUSTRATIVE UNTIL PUBLISHED
          </p>
        </div>
      </Reveal>
    </section>
  );
}
