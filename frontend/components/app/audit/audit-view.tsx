"use client";

import { useState } from "react";
import { endpoints } from "@/lib/api/endpoints";
import { useApi } from "@/lib/api/hooks";
import { cn } from "@/lib/utils";
import { AuditTable } from "../audit-table";
import { useCan } from "../me-provider";
import { Btn, ErrorState, Field, LoadingBlock, Panel, inputCls, selectCls } from "../ui";

const PAGE = 50;

export function AuditView() {
  const isAdmin = useCan("workspace.admin");
  const [tripId, setTripId] = useState("");
  const [entity, setEntity] = useState("");
  const [action, setAction] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [offset, setOffset] = useState(0);
  const trips = useApi("audit:trips", () => endpoints.trips({ limit: 100 }));
  // Brokers must scope to one trip (spec §8); admins may browse everything.
  const ready = isAdmin || !!tripId;
  const key = ready ? `audit:${tripId}:${entity}:${action}:${from}:${to}:${offset}` : null;
  const events = useApi(key, () =>
    endpoints.auditEvents({
      trip_id: tripId || undefined,
      entity_type: entity || undefined,
      action: action || undefined,
      date_from: from ? new Date(`${from}T00:00:00`).toISOString() : undefined,
      date_to: to ? new Date(`${to}T23:59:59`).toISOString() : undefined,
      limit: PAGE,
      offset,
    }),
  );
  const total = events.data?.total ?? 0;
  const reset = () => setOffset(0);

  return (
    <div className="mt-8 flex flex-col gap-4">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <Field label={isAdmin ? "Trip" : "Trip (required)"} htmlFor="au-trip">
          <select id="au-trip" value={tripId} onChange={(e) => { setTripId(e.target.value); reset(); }} className={selectCls}>
            <option value="">{isAdmin ? "All trips" : "Choose a trip"}</option>
            {(trips.data?.items ?? []).map((t) => (
              <option key={t.id} value={t.id}>{t.reference}{t.client_name ? ` · ${t.client_name}` : ""}</option>
            ))}
          </select>
        </Field>
        <Field label="Entity" htmlFor="au-entity">
          <select id="au-entity" value={entity} onChange={(e) => { setEntity(e.target.value); reset(); }} className={selectCls}>
            <option value="">Any</option>
            {["trip", "quote", "field", "flag", "proposal", "source_document", "operator", "user", "workspace", "invite"].map((x) => (
              <option key={x} value={x}>{x}</option>
            ))}
          </select>
        </Field>
        <Field label="Action" htmlFor="au-action">
          <input id="au-action" value={action} onChange={(e) => { setAction(e.target.value); reset(); }} placeholder="field.verify" className={cn(inputCls, "font-mono text-[12.5px]")} />
        </Field>
        <Field label="From" htmlFor="au-from">
          <input id="au-from" type="date" value={from} onChange={(e) => { setFrom(e.target.value); reset(); }} className={cn(inputCls, "[color-scheme:dark]")} />
        </Field>
        <Field label="To" htmlFor="au-to">
          <input id="au-to" type="date" value={to} onChange={(e) => { setTo(e.target.value); reset(); }} className={cn(inputCls, "[color-scheme:dark]")} />
        </Field>
      </div>

      <Panel
        title="Events"
        sub={events.data ? `${total} event${total === 1 ? "" : "s"} · click one to see its before/after diff` : undefined}
        bodyClassName="p-0 sm:p-0"
        className={cn(events.refreshing && "opacity-70")}
      >
        {!ready ? (
          <p className="px-5 py-10 text-center text-sm text-fg-dim">Brokers see the audit trail one trip at a time. Pick a trip above.</p>
        ) : events.loading ? (
          <div className="p-5"><LoadingBlock rows={6} /></div>
        ) : events.error && !events.data ? (
          <div className="p-5"><ErrorState error={events.error} onRetry={events.reload} /></div>
        ) : (
          <AuditTable events={events.data?.items ?? []} />
        )}
      </Panel>

      {ready && total > PAGE && (
        <div className="flex items-center justify-between text-xs text-fg-dim">
          <span>
            {offset + 1}–{Math.min(offset + PAGE, total)} of {total}
          </span>
          <div className="flex gap-2">
            <Btn size="xs" disabled={offset === 0} onClick={() => setOffset((o) => Math.max(0, o - PAGE))}>Newer</Btn>
            <Btn size="xs" disabled={offset + PAGE >= total} onClick={() => setOffset((o) => o + PAGE)}>Older</Btn>
          </div>
        </div>
      )}
    </div>
  );
}
