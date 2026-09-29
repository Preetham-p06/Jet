import type { Metadata } from "next";
import { OperatorsView } from "@/components/app/operators/operators-view";
import { PageHeader } from "@/components/app/ui";
import { verifySession } from "@/lib/dal";

export const metadata: Metadata = { title: "Operators" };

export default async function OperatorsPage() {
  await verifySession();
  return (
    <div className="mx-auto w-full max-w-6xl">
      <PageHeader
        eyebrow="Directory"
        title="Operators"
        lead="Everyone you request quotes from, with their quote history and response times."
      />
      <OperatorsView />
    </div>
  );
}
