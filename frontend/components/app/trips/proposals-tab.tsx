"use client";

import { useState } from "react";
import { FileSignature, Plus } from "lucide-react";
import { endpoints } from "@/lib/api/endpoints";
import { useApi, useMutation } from "@/lib/api/hooks";
import { cn } from "@/lib/utils";
import { useMe } from "../me-provider";
import { fmtRelative, formatCents } from "../fmt";
import { ProposalBuilder } from "../proposals/proposal-builder";
import { ProposalStatusPill } from "../status";
import { Btn, EmptyState, ErrorState, InlineError, LoadingBlock, Panel } from "../ui";
import { useTrip } from "./trip-context";

export function ProposalsTab() {
  const { tripId, trip, version, bump } = useTrip();
  const me = useMe();
  const list = useApi(`proposals:${tripId}`, () => endpoints.tripProposals(tripId), version);
  const [picked, setPicked] = useState<string | null>(null);
  const create = useMutation(() =>
    endpoints.createProposal(tripId, {
      markup_pct: me.workspace.default_markup_pct ?? null,
      title: trip ? `Private charter options · ${trip.reference}` : null,
      client_name: trip?.client_name ?? null,
    }),
  );

  const items = list.data?.items ?? [];
  const active = picked ?? items.find((p) => p.status === "draft" || p.status === "sent")?.id ?? items[0]?.id ?? null;

  async function onCreate() {
    const p = await create.run();
    if (p) {
      setPicked(p.id);
      bump();
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <Panel
        title="Proposals"
        sub="Build a client-ready proposal from eligible quotes. Only fully priced, reviewed quotes can be offered."
        actions={
          <Btn tone="primary" onClick={onCreate} pending={create.pending}>
            {!create.pending && <Plus className="h-3.5 w-3.5" aria-hidden="true" />} New proposal
          </Btn>
        }
        bodyClassName={cn(items.length ? "p-3 sm:p-3" : undefined)}
      >
        <InlineError error={create.error} className="mb-3" />
        {list.loading ? (
          <LoadingBlock rows={2} />
        ) : list.error && !list.data ? (
          <ErrorState error={list.error} onRetry={list.reload} />
        ) : !items.length ? (
          <EmptyState icon={<FileSignature className="h-5 w-5" strokeWidth={1.75} aria-hidden="true" />} title="No proposals yet">
            Create one to preselect every eligible quote, recommended first, at your default markup.
          </EmptyState>
        ) : (
          <ul className="flex gap-2 overflow-x-auto pb-1 [scrollbar-width:thin]">
            {items.map((p) => (
              <li key={p.id} className="shrink-0">
                <button
                  type="button"
                  onClick={() => setPicked(p.id)}
                  aria-pressed={p.id === active}
                  className={cn(
                    "flex w-[230px] flex-col gap-1.5 rounded-xl border px-3 py-2.5 text-left transition-colors",
                    p.id === active ? "border-cyan/35 bg-cyan/[0.05]" : "border-line hover:border-line-strong",
                  )}
                >
                  <span className="flex items-center justify-between gap-2">
                    <ProposalStatusPill status={p.status} />
                    <span className="text-[11px] text-fg-dim">{fmtRelative(p.updated_at)}</span>
                  </span>
                  <span className="truncate text-[13px] text-fg">{p.title}</span>
                  <span className="text-[11.5px] text-fg-dim">
                    {p.option_count} options · {p.markup_pct}% ·{" "}
                    <span className="tabular font-mono text-fg-muted">{formatCents(p.recommended_client_total_cents)}</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </Panel>

      {active && (
        <ProposalBuilder
          key={active}
          proposalId={active}
          onChanged={() => {
            list.reload();
            bump();
          }}
          onOpen={(id) => setPicked(id)}
        />
      )}
    </div>
  );
}
