import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { NewTripForm } from "@/components/app/trips/new-trip-form";
import { PageHeader } from "@/components/app/ui";
import { verifySession } from "@/lib/dal";

export const metadata: Metadata = { title: "New trip" };

export default async function NewTripPage() {
  await verifySession();
  return (
    <div className="mx-auto w-full max-w-6xl">
      <Link href="/trips" className="inline-flex items-center gap-1.5 text-xs text-fg-dim hover:text-fg">
        <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" /> Trips
      </Link>
      <PageHeader
        className="mt-3"
        eyebrow="New charter request"
        title="Create a trip"
        lead="Legs, passengers and client preferences. Operators you request quotes from are added on the trip's overview."
      />
      <NewTripForm />
    </div>
  );
}
