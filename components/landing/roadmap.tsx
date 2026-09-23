import { SectionHeader } from "@/components/ui/section-header";
import { RevealGroup, RevealItem } from "@/components/ui/reveal";
import { FlightDefs, FlightPath } from "@/components/ui/flight-path";
import { ROADMAP } from "@/lib/demo-data";
import { cn } from "@/lib/utils";

const PATH = "M20 8 C 34 120, 6 260, 20 400 S 30 520, 20 560";

export function Roadmap() {
  return (
    <section className="container-x py-24 sm:py-32">
      <div className="grid gap-12 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-16">
        <div className="lg:sticky lg:top-32 lg:self-start">
          <SectionHeader
            eyebrow="Platform"
            title="Quote intelligence is just the beginning."
            lead="Everything JetStream learns from quotes compounds into the rest of the brokerage workflow. Only the first stage exists today; the rest is direction, not promise."
          />
        </div>

        <RevealGroup as="ol" className="relative pl-14" staggerChildren={0.1}>
          <svg
            viewBox="0 0 40 568"
            preserveAspectRatio="none"
            className="absolute inset-y-0 left-0 h-full w-10"
            aria-hidden="true"
          >
            <FlightDefs id="rm" />
            <FlightPath d={PATH} defsId="rm" strokeWidth={1.6} dots={2} dotDuration={9} />
          </svg>

          {ROADMAP.map((item) => {
            const now = item.status === "Now";
            return (
              <RevealItem as="li" key={item.title} className="relative pb-10 last:pb-0">
                <span
                  aria-hidden="true"
                  className={cn(
                    "absolute -left-[41px] top-[9px] h-3 w-3 rounded-full border",
                    now
                      ? "border-cyan bg-ice shadow-[0_0_14px_rgba(89,217,255,0.9)]"
                      : "border-white/25 bg-[#0d121a]",
                  )}
                />
                <div className="flex flex-wrap items-center gap-3">
                  <h3 className={cn("text-[18px] font-semibold tracking-[-0.01em]", now ? "text-fg" : "text-fg-muted")}>
                    {item.title}
                  </h3>
                  <span
                    className={cn(
                      "rounded-full border px-2 py-0.5 font-mono text-[10px] tracking-[0.14em]",
                      now ? "border-cyan/35 bg-cyan/10 text-cyan" : "border-line text-fg-dim",
                    )}
                  >
                    {item.status.toUpperCase()}
                  </span>
                </div>
                <p className="mt-1.5 max-w-lg text-[14px] leading-relaxed text-fg-muted">{item.detail}</p>
              </RevealItem>
            );
          })}
        </RevealGroup>
      </div>
    </section>
  );
}
