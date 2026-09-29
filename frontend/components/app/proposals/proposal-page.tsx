"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { useCan } from "../me-provider";
import { EmptyState, PageHeader } from "../ui";
import { ProposalBuilder } from "./proposal-builder";

export function ProposalPage({ tripId, proposalId }: { tripId: string; proposalId: string }) {
  const router = useRouter();
  const canManage = useCan("proposal.manage");
  return (
    <div className="mx-auto w-full max-w-[1320px]">
      <Link href={`/trips/${tripId}?tab=proposals`} className="inline-flex items-center gap-1.5 text-xs text-fg-dim hover:text-fg">
        <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" /> Trip proposals
      </Link>
      <PageHeader className="mb-6 mt-3" eyebrow="Proposal" title="Proposal builder" />
      {canManage ? (
        <ProposalBuilder
          proposalId={proposalId}
          onOpen={(id) => router.push(`/trips/${tripId}/proposals/${id}`)}
        />
      ) : (
        <EmptyState title="Brokers only">Proposals are managed by brokers and admins.</EmptyState>
      )}
    </div>
  );
}
