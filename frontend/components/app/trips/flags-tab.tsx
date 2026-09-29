"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { ShieldCheck, Undo2 } from "lucide-react";
import { endpoints, type Flag, type FlagStatus } from "@/lib/api/endpoints";
import { useApi, useMutation } from "@/lib/api/hooks";
import { cn } from "@/lib/utils";
import { useCan } from "../me-provider";
import { FlagResolveDialog, RESOLUTION_LABEL } from "../flag-resolve-dialog";
import { fmtRelative, humanize } from "../fmt";
import { SeverityIcon, SeverityPill } from "../status";
import { Btn, EmptyState, ErrorState, InlineError, LoadingBlock, Panel, Pill, Segmented } from "../ui";
import { useTrip } from "./trip-context";

const SEV_ORDER = { critical: 0, warning: 1, info: 2 } as const;

export function FlagsTab() {
  const { tripId, version, bump } = useTrip();
  const canResolve = useCan("flag.resolve");
  const [status, setStatus] = useState<FlagStatus | "all">("open");
  const flags = useApi(`flags:${tripId}:${status}`, () =>
    endpoints.flags(tripId, status === "all" ? {} : { status }),
  version);
  const quotes = useApi(`quotes:${tripId}`, () => endpoints.quotes(tripId), version);
  const [resolving, setResolving] = useState<Flag | null>(null);

  const names = useMemo(
    () => new Map((quotes.data?.items ?? []).map((q) => [q.id, q.operator_name])),
    [quotes.data],
  );

  const groups = useMemo(() => {
    const m = new Map<string, Flag[]>();
    for (const f of flags.data?.items ?? []) {
      const k = f.quote_id ?? "trip";
      m.set(k, [...(m.get(k) ?? []), f]);
    }
    for (const list of m.values())
      list.sort((a, b) => Number(b.blocking) - Number(a.blocking) || SEV_ORDER[a.severity] - SEV_ORDER[b.severity]);
    return [...m.entries()].sort(
      (a, b) => b[1].filter((f) => f.blocking).length - a[1].filter((f) => f.blocking).length,
    );
  }, [flags.data]);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Segmented
          label="Flag status"
          value={status}
          onChange={setStatus}
          options={[
            { value: "open", label: "Open" },
            { value: "resolved", label: "Resolved" },
            { value: "dismissed", label: "Dismissed" },
            { value: "all", label: "All" },
          ]}
        />
        <p className="text-xs text-fg-dim">
          Warning and critical flags block proposals. Info flags are notes; the engine already took the conservative reading.
        </p>
      </div>

      {flags.loading ? (
        <Panel>
          <LoadingBlock rows={4} label="Loading flags" />
        </Panel>
      ) : flags.error && !flags.data ? (
        <ErrorState error={flags.error} onRetry={flags.reload} />
      ) : groups.length === 0 ? (
        <Panel>
          <EmptyState icon={<ShieldCheck className="h-5 w-5" strokeWidth={1.75} aria-hidden="true" />} title={status === "open" ? "No open flags" : "Nothing here"}>
            {status === "open" ? "Every quote passed validation, or its flags were resolved." : "Try another filter."}
          </EmptyState>
        </Panel>
      ) : (
        groups.map(([quoteId, list]) => {
          const name = quoteId === "trip" ? "Trip" : (names.get(quoteId) ?? "Quote");
          const blocking = list.filter((f) => f.blocking && f.status === "open").length;
          return (
            <Panel
              key={quoteId}
              title={
                quoteId === "trip" ? (
                  name
                ) : (
                  <Link href={`/trips/${tripId}/quotes/${quoteId}`} className="hover:text-cyan">
                    {name}
                  </Link>
                )
              }
              sub={`${list.length} flag${list.length === 1 ? "" : "s"}${blocking ? ` · ${blocking} blocking` : ""}`}
              bodyClassName="p-0 sm:p-0"
            >
              <ul className="divide-y divide-line">
                {list.map((f) => (
                  <FlagRow key={f.id} flag={f} canResolve={canResolve} onResolve={() => setResolving(f)} onChanged={bump} />
                ))}
              </ul>
            </Panel>
          );
        })
      )}

      <FlagResolveDialog
        flag={resolving}
        operatorName={resolving?.quote_id ? names.get(resolving.quote_id) : undefined}
        onClose={() => setResolving(null)}
        onResolved={bump}
      />
    </div>
  );
}

function FlagRow({
  flag,
  canResolve,
  onResolve,
  onChanged,
}: {
  flag: Flag;
  canResolve: boolean;
  onResolve: () => void;
  onChanged: () => void;
}) {
  const reopen = useMutation(() => endpoints.reopenFlag(flag.id));
  const open = flag.status === "open";
  return (
    <li className={cn("flex flex-col gap-2 px-4 py-3.5 sm:flex-row sm:items-start sm:gap-4 sm:px-5", !open && "opacity-70")}>
      <SeverityIcon severity={flag.severity} className="mt-0.5 hidden sm:block" />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[13.5px] font-medium text-fg">{humanize(flag.type)}</span>
          <SeverityPill severity={flag.severity} blocking={flag.blocking && open} />
          {flag.fee_category && <Pill>{humanize(flag.fee_category)}</Pill>}
        </div>
        <p className="mt-1 text-[13px] leading-relaxed text-fg-muted">{flag.message}</p>
        {!open && (
          <p className="mt-1 text-xs text-fg-dim">
            {humanize(flag.status)}
            {flag.resolution && ` · ${RESOLUTION_LABEL[flag.resolution]?.label ?? humanize(flag.resolution)}`}
            {flag.resolution_note && ` · “${flag.resolution_note}”`}
            {flag.resolved_at && ` · ${fmtRelative(flag.resolved_at)}`}
          </p>
        )}
        <InlineError error={reopen.error} className="mt-1" />
      </div>
      <div className="flex shrink-0 items-center gap-2" title={canResolve ? undefined : "Broker review required"}>
        {open ? (
          <Btn size="sm" tone={flag.blocking ? "amber" : "default"} disabled={!canResolve} onClick={onResolve}>
            Resolve
          </Btn>
        ) : flag.resolution !== "auto_cleared" ? (
          <Btn
            size="sm"
            tone="ghost"
            disabled={!canResolve}
            pending={reopen.pending}
            onClick={async () => {
              if (await reopen.run()) onChanged();
            }}
          >
            <Undo2 className="h-3.5 w-3.5" aria-hidden="true" /> Reopen
          </Btn>
        ) : null}
      </div>
    </li>
  );
}
