import type { Metadata } from "next";
import { ProposalPage } from "@/components/app/proposals/proposal-page";
import { verifySession } from "@/lib/dal";

export const metadata: Metadata = { title: "Proposal" };

export default async function Page(props: PageProps<"/trips/[tripId]/proposals/[proposalId]">) {
  await verifySession();
  const { tripId, proposalId } = await props.params;
  return <ProposalPage tripId={tripId} proposalId={proposalId} />;
}
