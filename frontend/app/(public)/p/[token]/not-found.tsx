import { AmbientBackground } from "@/components/landing/ambient-background";
import { ProposalNotice } from "@/components/proposal/proposal-notice";
import { LogoMark } from "@/components/ui/logo";

export default function ProposalNotFound() {
  return (
    <>
      <AmbientBackground />
      <main id="main" className="relative z-10 flex min-h-dvh flex-1 flex-col items-center justify-center px-4 py-16">
        <ProposalNotice
          code="404"
          title="This proposal link isn't available"
          body="It may have expired or been withdrawn. Please contact your broker for a new link."
        />
        <p className="mt-8 inline-flex items-center gap-2 text-xs text-fg-dim">
          <LogoMark className="h-4 w-4" gradientId="js-mark-grad-public-404" /> Prepared with JetStream AI
        </p>
      </main>
    </>
  );
}
