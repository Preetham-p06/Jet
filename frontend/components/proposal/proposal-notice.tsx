import { FileX2 } from "lucide-react";
import { GlassCard } from "@/components/ui/glass-card";

/** Friendly full-page notice for missing (404) or superseded (410) proposal links. */
export function ProposalNotice({ code, title, body }: { code: string; title: string; body: string }) {
  return (
    <GlassCard glass edge className="shadow-shell my-auto w-full max-w-[480px] p-8 text-center">
      <span className="mx-auto grid h-12 w-12 place-items-center rounded-full border border-cyan/20 bg-cyan/[0.06] text-cyan">
        <FileX2 className="h-5 w-5" strokeWidth={1.75} aria-hidden="true" />
      </span>
      <p className="mt-5 font-mono text-[11px] tracking-[0.18em] text-fg-dim">{code}</p>
      <h1 className="mt-2 text-xl font-semibold text-gradient-ice">{title}</h1>
      <p className="mt-3 text-sm leading-relaxed text-fg-muted">{body}</p>
    </GlassCard>
  );
}
