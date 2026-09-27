import { Ban, FileSearch, Lock, ShieldCheck, UserCheck, type LucideIcon } from "lucide-react";
import { SectionHeader } from "@/components/ui/section-header";
import { RevealGroup, RevealItem } from "@/components/ui/reveal";
import { SECURITY_POINTS } from "@/lib/demo-data";

const ICONS: LucideIcon[] = [ShieldCheck, Lock, FileSearch, UserCheck, Ban];

export function Security() {
  return (
    <section id="security" className="container-x py-20 sm:py-24">
      <SectionHeader
        align="center"
        eyebrow="Trust"
        title="Built for sensitive deal workflows."
        lead="Quotes carry client names, routes and six-figure prices. JetStream treats them that way."
      />
      <RevealGroup as="ul" className="mt-12 grid gap-3 sm:grid-cols-2 lg:grid-cols-5" staggerChildren={0.06}>
        {SECURITY_POINTS.map((p, i) => {
          const Icon = ICONS[i];
          return (
            <RevealItem as="li" key={p.title} className="surface-card p-5">
              <Icon className="h-4.5 w-4.5 text-cyan" aria-hidden="true" />
              <h3 className="mt-4 text-[14.5px] font-semibold text-fg">{p.title}</h3>
              <p className="mt-1.5 text-[12.5px] leading-relaxed text-fg-muted">{p.detail}</p>
            </RevealItem>
          );
        })}
      </RevealGroup>
      <p className="mt-6 text-center text-[12px] text-fg-dim">
        Formal certifications will be listed here only once they are complete and verified.
      </p>
    </section>
  );
}
