import type { Metadata } from "next";
import { AuditView } from "@/components/app/audit/audit-view";
import { EmptyState, PageHeader } from "@/components/app/ui";
import { verifySession } from "@/lib/dal";

export const metadata: Metadata = { title: "Audit log" };

export default async function AuditPage() {
  const me = await verifySession();
  const allowed = me.capabilities.includes("audit.view");
  return (
    <div className="mx-auto w-full max-w-6xl">
      <PageHeader
        eyebrow="Compliance"
        title="Audit log"
        lead="Every review, edit, flag resolution, proposal and settings change, with who did it and what changed."
      />
      {allowed ? (
        <AuditView />
      ) : (
        <EmptyState className="mt-8" title="Brokers and admins only">
          The audit log isn&apos;t available to your role.
        </EmptyState>
      )}
    </div>
  );
}
