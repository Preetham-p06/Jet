import { Database, FileText, Globe, Inbox, LayoutGrid, Mail, type LucideIcon } from "lucide-react";
import { SectionHeader } from "@/components/ui/section-header";
import { RevealGroup, RevealItem } from "@/components/ui/reveal";
import { INTEGRATIONS } from "@/lib/demo-data";

const ICONS: Record<(typeof INTEGRATIONS)[number]["kind"], LucideIcon> = {
  mail: Mail,
  pdf: FileText,
  crm: Database,
  market: Globe,
  portal: LayoutGrid,
};

export function Integrations() {
  return (
    <section className="container-x py-20 sm:py-24">
      <div className="grid gap-10 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:items-center lg:gap-16">
        <SectionHeader
          eyebrow="Integrations"
          title="Meets your quotes where they already arrive."
          lead="Planned connectors for the channels operators actually use. None are live yet, and each one is labeled that way until it is."
        />
        <RevealGroup as="ul" className="grid grid-cols-2 gap-3 sm:grid-cols-3" staggerChildren={0.06}>
          {INTEGRATIONS.map((it) => {
            const Icon = it.kind === "mail" && it.label === "Gmail" ? Inbox : ICONS[it.kind];
            return (
              <RevealItem
                as="li"
                key={it.label}
                className="surface-card flex flex-col gap-4 p-4 transition-colors duration-200 hover:border-white/15"
              >
                <span className="grid h-9 w-9 place-items-center rounded-lg border border-line bg-white/[0.03] text-fg-muted">
                  <Icon className="h-4 w-4" aria-hidden="true" />
                </span>
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[13.5px] font-medium text-fg">{it.label}</span>
                  <span className="rounded-full border border-line px-2 py-0.5 font-mono text-[9.5px] tracking-[0.12em] text-fg-dim">
                    PLANNED
                  </span>
                </div>
              </RevealItem>
            );
          })}
        </RevealGroup>
      </div>
    </section>
  );
}
