import { Reveal } from "@/components/ui/reveal";
import { TRUST_POINTS } from "@/lib/demo-data";

export function TrustStrip() {
  return (
    <section aria-label="Built for modern charter brokerages" className="container-x mt-4 sm:mt-8">
      <Reveal className="flex flex-col items-center gap-4 border-y border-line py-6 sm:flex-row sm:justify-between">
        <p className="eyebrow">Built for modern charter brokerages</p>
        <ul className="flex flex-wrap justify-center gap-x-6 gap-y-2 text-[13.5px] text-fg-muted">
          {TRUST_POINTS.map((p, i) => (
            <li key={p} className="flex items-center gap-2.5">
              {i > 0 && <span className="hidden h-1 w-1 rounded-full bg-fg-dim/60 sm:block" aria-hidden="true" />}
              <span className={i === TRUST_POINTS.length - 1 ? "text-fg-dim" : undefined}>{p}</span>
            </li>
          ))}
        </ul>
      </Reveal>
    </section>
  );
}
