"use client";

import { useMemo, useState } from "react";
import { Building2, Clock, Plus, Search, X } from "lucide-react";
import { endpoints, type RequestChannel, type TripOperator } from "@/lib/api/endpoints";
import { useApi, useMutation } from "@/lib/api/hooks";
import { cn } from "@/lib/utils";
import { useCan } from "../me-provider";
import { fmtDateTime, fmtHours, fmtLocal, formatCents, humanize, toLocalInput } from "../fmt";
import { RfqStatusPill } from "../status";
import {
  Btn,
  Dialog,
  EmptyState,
  ErrorState,
  Field,
  InlineError,
  LoadingBlock,
  Panel,
  TableScroll,
  inputCls,
  selectCls,
  tdCls,
  thCls,
} from "../ui";
import { useTrip } from "./trip-context";

function responseMinutes(r: TripOperator): number | null {
  if (r.response_minutes != null) return r.response_minutes;
  if (!r.responded_at) return null;
  return (new Date(r.responded_at).getTime() - new Date(r.requested_at).getTime()) / 60000;
}

export function OverviewTab() {
  const { trip, tripId, version, bump, goTab } = useTrip();
  const rfq = useApi(`rfq:${tripId}`, () => endpoints.tripOperators(tripId), version);
  const [adding, setAdding] = useState(false);
  const canWrite = useCan("trip.write");
  const c = trip?.counts;

  const rows = useMemo(() => rfq.data?.items ?? [], [rfq.data]);
  const responded = rows.map(responseMinutes).filter((m): m is number => m != null);
  const maxResp = Math.max(1, ...responded);
  const median = responded.length
    ? [...responded].sort((a, b) => a - b)[Math.floor((responded.length - 1) / 2)]
    : null;

  const stats = [
    { label: "Operators contacted", value: c?.operators_requested ?? rows.length },
    { label: "Quotes received", value: c?.quotes ?? trip?.quote_count ?? 0, go: "quotes" as const },
    { label: "Declined", value: c?.operators_declined ?? rows.filter((r) => r.status === "declined").length },
    { label: "Pending review", value: c?.pending_review ?? 0, go: "review" as const, warn: true },
    { label: "Blocking flags", value: c?.open_blocking_flags ?? trip?.open_flag_count ?? 0, go: "flags" as const, warn: true },
  ];

  return (
    <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
      <div className="flex min-w-0 flex-col gap-5">
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          {stats.map((s) => {
            const inner = (
              <>
                <p className="font-mono text-[9.5px] uppercase tracking-[0.14em] text-fg-dim">{s.label}</p>
                <p
                  className={cn(
                    "tabular mt-1.5 text-[24px] font-semibold leading-none tracking-[-0.02em]",
                    s.warn && s.value > 0 ? "text-amber" : "text-fg",
                  )}
                >
                  {trip ? s.value : "–"}
                </p>
              </>
            );
            return (
              <li key={s.label}>
                {s.go ? (
                  <button
                    type="button"
                    onClick={() => goTab(s.go)}
                    className="surface-card block w-full rounded-xl p-3.5 text-left transition-colors hover:border-line-strong"
                  >
                    {inner}
                  </button>
                ) : (
                  <div className="surface-card rounded-xl p-3.5">{inner}</div>
                )}
              </li>
            );
          })}
        </ul>

        <Panel
          title="Operator requests"
          sub={
            median != null
              ? `Median response ${fmtHours(median / 60)} across ${responded.length} responses`
              : "Track who you asked, who answered and how fast."
          }
          actions={
            canWrite ? (
              <Btn onClick={() => setAdding(true)}>
                <Plus className="h-3.5 w-3.5" aria-hidden="true" /> Add operators
              </Btn>
            ) : undefined
          }
          bodyClassName="p-0 sm:p-0"
        >
          {rfq.loading ? (
            <div className="p-5">
              <LoadingBlock rows={4} label="Loading operator requests" />
            </div>
          ) : rfq.error && !rfq.data ? (
            <div className="p-5">
              <ErrorState error={rfq.error} onRetry={rfq.reload} />
            </div>
          ) : rows.length === 0 ? (
            <EmptyState
              icon={<Building2 className="h-5 w-5" strokeWidth={1.75} aria-hidden="true" />}
              title="No operators requested yet"
              action={canWrite ? <Btn onClick={() => setAdding(true)}>Add operators</Btn> : undefined}
            >
              Add the operators you sent this RFQ to. Response times feed operator analytics.
            </EmptyState>
          ) : (
            <TableScroll className="px-5 pt-3">
              <table className="w-full min-w-[640px] border-separate border-spacing-0 text-[13px]">
                <thead>
                  <tr>
                    <th className={thCls}>Operator</th>
                    <th className={thCls}>Status</th>
                    <th className={thCls}>Requested</th>
                    <th className={cn(thCls, "w-[34%]")}>Response time</th>
                    <th className={thCls}>
                      <span className="sr-only">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <RfqRow key={r.id} row={r} maxResp={maxResp} onChanged={bump} canWrite={canWrite} />
                  ))}
                </tbody>
              </table>
            </TableScroll>
          )}
        </Panel>
      </div>

      <div className="flex min-w-0 flex-col gap-5">
        <Panel title="Itinerary">
          {trip ? (
            <ol className="flex flex-col gap-3">
              {trip.legs.map((l) => (
                <li key={l.id} className="flex items-center gap-3">
                  <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full border border-line font-mono text-[11px] text-fg-dim">
                    {l.seq}
                  </span>
                  <div className="min-w-0">
                    <p className="font-mono text-[13px] text-fg">
                      {l.origin_icao} <span className="text-fg-dim">→</span> {l.destination_icao}
                    </p>
                    <p className="text-xs text-fg-dim">
                      {fmtLocal(l.depart_local, l.depart_tz, true)} · {l.depart_tz}
                    </p>
                  </div>
                </li>
              ))}
            </ol>
          ) : (
            <LoadingBlock rows={2} />
          )}
        </Panel>
        {trip && (
          <Panel title="Client & preferences">
            <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-2 text-[13px]">
              <dt className="text-fg-dim">Client</dt>
              <dd className="text-fg">{trip.client_name ?? "—"}</dd>
              <dt className="text-fg-dim">Trip type</dt>
              <dd className="text-fg">{humanize(trip.trip_type)}</dd>
              <dt className="text-fg-dim">Wi-Fi</dt>
              <dd className="text-fg">{trip.preferences?.wifi_required ? "Required" : "Not required"}</dd>
              <dt className="text-fg-dim">Catering</dt>
              <dd className="text-fg">{trip.preferences?.catering_required ? "Required" : "Not required"}</dd>
              <dt className="text-fg-dim">Budget</dt>
              <dd className="tabular text-fg">{formatCents(trip.preferences?.max_budget_cents)}</dd>
              {trip.notes && (
                <>
                  <dt className="text-fg-dim">Notes</dt>
                  <dd className="text-fg-muted">{trip.notes}</dd>
                </>
              )}
            </dl>
          </Panel>
        )}
      </div>

      <AddOperatorsDialog open={adding} onClose={() => setAdding(false)} onAdded={bump} existing={rows} />
    </div>
  );
}

function RfqRow({
  row,
  maxResp,
  onChanged,
  canWrite,
}: {
  row: TripOperator;
  maxResp: number;
  onChanged: () => void;
  canWrite: boolean;
}) {
  const { tripId } = useTrip();
  const patch = useMutation((body: Parameters<typeof endpoints.patchTripOperator>[2]) =>
    endpoints.patchTripOperator(tripId, row.id, body),
  );
  const mins = responseMinutes(row);

  return (
    <tr>
      <td className={tdCls}>
        <p className="text-fg">{row.operator_name}</p>
        <p className="text-xs text-fg-dim">{humanize(row.channel)}</p>
      </td>
      <td className={tdCls}>
        <RfqStatusPill status={row.status} />
        {row.declined_reason && <p className="mt-1 max-w-[180px] truncate text-xs text-fg-dim">{row.declined_reason}</p>}
      </td>
      <td className={cn(tdCls, "whitespace-nowrap text-fg-muted")}>{fmtDateTime(row.requested_at)}</td>
      <td className={tdCls}>
        {mins != null ? (
          <div className="flex items-center gap-3" title={`Responded ${fmtDateTime(row.responded_at)}`}>
            <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/[0.05]">
              <span
                className={cn("block h-full rounded-full", row.status === "declined" ? "bg-fg-dim/60" : "bg-[#5B8CFF]")}
                style={{ width: `${Math.max(4, (mins / maxResp) * 100)}%` }}
              />
            </span>
            <span className="tabular w-14 text-right font-mono text-[12px] text-fg">{fmtHours(mins / 60)}</span>
          </div>
        ) : (
          <span className="inline-flex items-center gap-1.5 text-xs text-fg-dim">
            <Clock className="h-3.5 w-3.5" aria-hidden="true" /> Awaiting reply
          </span>
        )}
      </td>
      <td className={cn(tdCls, "text-right")}>
        {canWrite && row.status === "requested" && (
          <Btn
            size="xs"
            tone="ghost"
            pending={patch.pending}
            onClick={async () => {
              const r = await patch.run({ status: "declined", responded_at: new Date().toISOString() });
              if (r) onChanged();
            }}
          >
            Mark declined
          </Btn>
        )}
        {canWrite && row.status === "declined" && (
          <Btn
            size="xs"
            tone="ghost"
            pending={patch.pending}
            onClick={async () => {
              const r = await patch.run({ status: "requested", responded_at: null, declined_reason: null });
              if (r) onChanged();
            }}
          >
            Undo
          </Btn>
        )}
        <InlineError error={patch.error} className="mt-1 justify-end" />
      </td>
    </tr>
  );
}

function AddOperatorsDialog({
  open,
  onClose,
  onAdded,
  existing,
}: {
  open: boolean;
  onClose: () => void;
  onAdded: () => void;
  existing: TripOperator[];
}) {
  const { tripId } = useTrip();
  const ops = useApi(open ? "operators:all" : null, () => endpoints.operators());
  const [q, setQ] = useState("");
  const [picked, setPicked] = useState<string[]>([]);
  const [newNames, setNewNames] = useState<string[]>([]);
  const [newName, setNewName] = useState("");
  const [channel, setChannel] = useState<RequestChannel>("email");
  const [requestedAt, setRequestedAt] = useState(() => toLocalInput(new Date()));
  const add = useMutation(() =>
    endpoints.addTripOperators(tripId, {
      operator_ids: picked,
      new_operators: newNames.map((name) => ({ name })),
      channel,
      requested_at: requestedAt ? new Date(requestedAt).toISOString() : null,
    }),
  );

  const already = new Set(existing.map((e) => e.operator_id));
  const list = (ops.data?.items ?? []).filter(
    (o) => !already.has(o.id) && (!q || o.name.toLowerCase().includes(q.toLowerCase())),
  );

  function close() {
    setPicked([]);
    setNewNames([]);
    setQ("");
    add.clear();
    onClose();
  }

  return (
    <Dialog
      open={open}
      onClose={close}
      title="Add operators to this RFQ"
      description="Pick operators from your directory or add new ones by name."
      wide
      footer={
        <>
          <Btn tone="ghost" onClick={close}>
            Cancel
          </Btn>
          <Btn
            tone="primary"
            pending={add.pending}
            disabled={picked.length + newNames.length === 0}
            onClick={async () => {
              const r = await add.run();
              if (r) {
                onAdded();
                close();
              }
            }}
          >
            Add {picked.length + newNames.length || ""}
          </Btn>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-fg-dim" aria-hidden="true" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Filter operators"
            aria-label="Filter operators"
            className={cn(inputCls, "pl-9")}
          />
        </div>
        <div className="max-h-56 overflow-y-auto rounded-xl border border-line">
          {ops.loading ? (
            <div className="p-3">
              <LoadingBlock rows={3} />
            </div>
          ) : ops.error ? (
            <ErrorState error={ops.error} onRetry={ops.reload} className="border-0" />
          ) : list.length === 0 ? (
            <p className="p-4 text-center text-xs text-fg-dim">No matching operators. Add one by name below.</p>
          ) : (
            <ul className="divide-y divide-line">
              {list.map((o) => {
                const on = picked.includes(o.id);
                return (
                  <li key={o.id}>
                    <label className="flex cursor-pointer items-center gap-3 px-3 py-2.5 text-[13px] hover:bg-white/[0.03]">
                      <input
                        type="checkbox"
                        checked={on}
                        onChange={() => setPicked((p) => (on ? p.filter((x) => x !== o.id) : [...p, o.id]))}
                        className="h-4 w-4 accent-[#59d9ff]"
                      />
                      <span className="flex-1 text-fg">{o.name}</span>
                      {o.home_base_icao && <span className="font-mono text-[11px] text-fg-dim">{o.home_base_icao}</span>}
                    </label>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <Field label="New operator" htmlFor="new-op">
          <div className="flex gap-2">
            <input
              id="new-op"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  if (newName.trim()) {
                    setNewNames((n) => [...n, newName.trim()]);
                    setNewName("");
                  }
                }
              }}
              placeholder="Operator name"
              className={inputCls}
            />
            <Btn
              onClick={() => {
                if (newName.trim()) {
                  setNewNames((n) => [...n, newName.trim()]);
                  setNewName("");
                }
              }}
              disabled={!newName.trim()}
            >
              Add
            </Btn>
          </div>
        </Field>
        {newNames.length > 0 && (
          <ul className="flex flex-wrap gap-1.5">
            {newNames.map((n, i) => (
              <li key={`${n}-${i}`} className="inline-flex items-center gap-1 rounded-full border border-line px-2.5 py-1 text-xs text-fg">
                {n}
                <button
                  type="button"
                  aria-label={`Remove ${n}`}
                  onClick={() => setNewNames((ns) => ns.filter((_, j) => j !== i))}
                  className="text-fg-dim hover:text-fg"
                >
                  <X className="h-3 w-3" aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
        )}

        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Channel" htmlFor="rfq-channel">
            <select
              id="rfq-channel"
              value={channel}
              onChange={(e) => setChannel(e.target.value as RequestChannel)}
              className={selectCls}
            >
              {(["email", "phone", "sms", "whatsapp", "portal", "other"] as const).map((c) => (
                <option key={c} value={c}>
                  {humanize(c)}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Requested at" htmlFor="rfq-at">
            <input
              id="rfq-at"
              type="datetime-local"
              value={requestedAt}
              onChange={(e) => setRequestedAt(e.target.value)}
              className={cn(inputCls, "[color-scheme:dark]")}
            />
          </Field>
        </div>
        <InlineError error={add.error} />
      </div>
    </Dialog>
  );
}
