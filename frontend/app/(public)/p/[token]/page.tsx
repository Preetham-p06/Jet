import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { AmbientBackground } from "@/components/landing/ambient-background";
import { PublicProposalView } from "@/components/proposal/public-proposal";
import { ProposalNotice } from "@/components/proposal/proposal-notice";
import { LogoMark } from "@/components/ui/logo";
import { ApiError } from "@/lib/api/errors";
import type { PublicProposal } from "@/lib/api/endpoints";
import { serverApi } from "@/lib/api/server";

export const metadata: Metadata = {
  title: "Charter proposal",
  robots: { index: false, follow: false, nocache: true, googleBot: { index: false, follow: false } },
  referrer: "no-referrer",
};

type Outcome = { kind: "ok"; proposal: PublicProposal } | { kind: "missing" } | { kind: "gone" } | { kind: "error" };

async function load(token: string): Promise<Outcome> {
  if (!/^[A-Za-z0-9_-]{16,128}$/.test(token)) return { kind: "missing" };
  try {
    // Never forward the broker's session: the public view is anonymous.
    const proposal = await serverApi<PublicProposal>(`/public/proposals/${encodeURIComponent(token)}`, { token: null });
    return { kind: "ok", proposal };
  } catch (e) {
    if (e instanceof ApiError && (e.status === 404 || e.status === 422)) return { kind: "missing" };
    if (e instanceof ApiError && e.status === 410) return { kind: "gone" };
    return { kind: "error" };
  }
}

/** Client-facing proposal link: server-rendered, noindex, no operator or fee data. */
export default async function PublicProposalPage(props: PageProps<"/p/[token]">) {
  const { token } = await props.params;
  const res = await load(token);
  // notFound() throws, so it stays outside the try in load().
  if (res.kind === "missing") notFound();

  return (
    <>
      <AmbientBackground />
      <main id="main" className="relative z-10 flex min-h-dvh flex-1 flex-col items-center px-4 py-10 sm:py-16">
        {res.kind === "ok" ? (
          <div className="relative w-full max-w-[1100px] overflow-hidden rounded-3xl border border-line bg-[linear-gradient(180deg,#111925_0%,#0b0f16_100%)] p-6 shadow-shell sm:p-10 lg:p-12">
            <div
              aria-hidden="true"
              className="pointer-events-none absolute -top-40 left-1/2 h-80 w-[720px] max-w-full -translate-x-1/2 rounded-full bg-[radial-gradient(circle,rgba(91,140,255,0.16),transparent_65%)] blur-2xl"
            />
            <div className="relative">
              <PublicProposalView token={token} initial={res.proposal} />
            </div>
          </div>
        ) : res.kind === "gone" ? (
          <ProposalNotice
            code="410"
            title="This proposal has been updated"
            body="Your broker revised this proposal, so this link no longer works. Please use the newest link they sent you, or contact them for a fresh one."
          />
        ) : (
          <ProposalNotice
            code="—"
            title="We couldn't load this proposal"
            body="Something went wrong on our side. Please refresh in a moment, or contact your broker."
          />
        )}
        <p className="mt-8 inline-flex items-center gap-2 text-xs text-fg-dim">
          <LogoMark className="h-4 w-4" gradientId="js-mark-grad-public" /> Prepared with JetStream AI
        </p>
      </main>
    </>
  );
}
