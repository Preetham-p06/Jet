import type { Metadata } from "next";
import { FileText } from "lucide-react";
import { AmbientBackground } from "@/components/landing/ambient-background";
import { GlassCard } from "@/components/ui/glass-card";
import { LogoMark } from "@/components/ui/logo";

export const metadata: Metadata = {
  title: "Charter proposal",
  robots: { index: false, follow: false, nocache: true, googleBot: { index: false, follow: false } },
  referrer: "no-referrer",
};

/** Client-facing proposal link. Placeholder: the proposal view lands with the dashboard package. */
export default async function PublicProposalPage(props: PageProps<"/p/[token]">) {
  await props.params; // token is consumed by the real view later

  return (
    <>
      <AmbientBackground />
      <main id="main" className="relative z-10 flex min-h-dvh flex-1 items-center justify-center px-4 py-16">
        <GlassCard glass edge className="shadow-shell w-full max-w-[480px] p-8 text-center">
          <span className="mx-auto grid h-12 w-12 place-items-center rounded-full border border-cyan/20 bg-cyan/[0.06] text-cyan">
            <FileText className="h-5 w-5" strokeWidth={1.75} aria-hidden="true" />
          </span>
          <h1 className="mt-5 text-xl font-semibold text-gradient-ice">Your charter proposal</h1>
          <p className="mt-2 text-sm text-fg-muted">Your broker&apos;s proposal will appear here.</p>
          <p className="mt-8 inline-flex items-center gap-2 text-xs text-fg-dim">
            <LogoMark className="h-4 w-4" /> Prepared with JetStream AI
          </p>
        </GlassCard>
      </main>
    </>
  );
}
