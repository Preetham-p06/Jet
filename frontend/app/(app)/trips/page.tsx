import type { Metadata } from "next";
import Link from "next/link";
import { Plus } from "lucide-react";
import { TripsList } from "@/components/app/trips/trips-list";
import { PageHeader } from "@/components/app/ui";
import { verifySession } from "@/lib/dal";

export const metadata: Metadata = { title: "Trips" };

export default async function TripsPage() {
  const me = await verifySession();
  const firstName = me.user.full_name.split(/\s+/)[0] ?? "";
  const canWrite = me.capabilities.includes("trip.write");

  return (
    <div className="mx-auto w-full max-w-6xl">
      <PageHeader
        eyebrow={me.workspace.name}
        title="Trips"
        lead={`${firstName ? `Welcome back, ${firstName}. ` : ""}Every open trip, its operator quotes and the true cost recommendation.`}
        actions={
          canWrite ? (
            <Link
              href="/trips/new"
              className="inline-flex h-10 items-center gap-1.5 rounded-full bg-[linear-gradient(135deg,#f2fdff_0%,#9fe9ff_38%,#5b8cff_100%)] px-4 text-sm font-medium text-bg-deep shadow-[0_8px_24px_-8px_rgba(89,217,255,0.55)] transition-shadow hover:shadow-[0_12px_32px_-8px_rgba(89,217,255,0.8)]"
            >
              <Plus className="h-4 w-4" aria-hidden="true" /> New trip
            </Link>
          ) : undefined
        }
      />
      <TripsList />
    </div>
  );
}
