import type { Metadata } from "next";
import { TripWorkspace } from "@/components/app/trips/trip-workspace";
import { isTripTab } from "@/components/app/trips/trip-tabs";
import { verifySession } from "@/lib/dal";

export const metadata: Metadata = { title: "Trip" };

export default async function TripPage(props: PageProps<"/trips/[tripId]">) {
  await verifySession();
  const { tripId } = await props.params;
  const { tab } = await props.searchParams;
  const t = Array.isArray(tab) ? tab[0] : tab;
  return <TripWorkspace key={tripId} tripId={tripId} initialTab={isTripTab(t) ? t : "overview"} />;
}
