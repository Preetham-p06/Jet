import type { Metadata } from "next";
import { QuoteDetailView } from "@/components/app/quotes/quote-detail";
import { verifySession } from "@/lib/dal";

export const metadata: Metadata = { title: "Quote" };

export default async function QuotePage(props: PageProps<"/trips/[tripId]/quotes/[quoteId]">) {
  await verifySession();
  const { tripId, quoteId } = await props.params;
  return <QuoteDetailView key={quoteId} tripId={tripId} quoteId={quoteId} />;
}
