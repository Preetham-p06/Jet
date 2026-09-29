"use client";

import { useState, type FormEvent } from "react";
import { Archive, Building2, Plus, Search } from "lucide-react";
import { endpoints, type Operator } from "@/lib/api/endpoints";
import { useApi, useMutation } from "@/lib/api/hooks";
import { cn } from "@/lib/utils";
import { useCan, useMe } from "../me-provider";
import { fmtDate, fmtHours } from "../fmt";
import { Btn, Dialog, EmptyState, ErrorState, Field, InlineError, LoadingBlock, Panel, Pill, TableScroll, inputCls, tdCls, textareaCls, thCls } from "../ui";

export function OperatorsView() {
  const me = useMe();
  const canCreate = useCan("trip.write");
  const canEdit = (me.user.role ?? me.role) !== "assistant";
  const canArchive = useCan("workspace.admin");
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [archived, setArchived] = useState(false);
  const [rev, setRev] = useState(0);
  const ops = useApi(`ops:${query}:${archived}`, () => endpoints.operators({ q: query || undefined, include_archived: archived }), rev);
  const [openId, setOpenId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const refresh = () => setRev((r) => r + 1);

  return (
    <div className="mt-8 flex flex-col gap-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <form
          role="search"
          onSubmit={(e) => {
            e.preventDefault();
            setQuery(q.trim());
          }}
          className="relative w-full sm:w-80"
        >
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-fg-dim" aria-hidden="true" />
          <input
            type="search"
            aria-label="Search operators"
            placeholder="Search name, alias or email domain"
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              if (!e.target.value) setQuery("");
            }}
            className={cn(inputCls, "pl-9")}
          />
        </form>
        <div className="flex items-center gap-3">
          <label className="inline-flex items-center gap-2 text-[12.5px] text-fg-muted">
            <input type="checkbox" checked={archived} onChange={(e) => setArchived(e.target.checked)} className="accent-[#59d9ff]" />
            Show archived
          </label>
          {canCreate && (
            <Btn tone="primary" onClick={() => setCreating(true)}>
              <Plus className="h-3.5 w-3.5" aria-hidden="true" /> Add operator
            </Btn>
          )}
        </div>
      </div>

      <Panel bodyClassName="p-0 sm:p-0">
        {ops.loading ? (
          <div className="p-5"><LoadingBlock rows={5} /></div>
        ) : ops.error && !ops.data ? (
          <div className="p-5"><ErrorState error={ops.error} onRetry={ops.reload} /></div>
        ) : !ops.data?.items.length ? (
          <EmptyState icon={<Building2 className="h-5 w-5" strokeWidth={1.75} aria-hidden="true" />} title={query ? "No operators match" : "No operators yet"}>
            Operators are added here, from a trip&apos;s RFQ list, or automatically when a quote names a new one.
          </EmptyState>
        ) : (
          <TableScroll className="px-5 pt-3">
            <table className="w-full min-w-[640px] border-separate border-spacing-0 text-[13px]">
              <thead>
                <tr>
                  <th className={thCls}>Operator</th>
                  <th className={thCls}>Contact</th>
                  <th className={thCls}>Home base</th>
                  <th className={thCls}>Source</th>
                  <th className={thCls}>Added</th>
                </tr>
              </thead>
              <tbody>
                {ops.data.items.map((o) => (
                  <tr key={o.id} onClick={() => setOpenId(o.id)} className={cn("cursor-pointer transition-colors hover:bg-white/[0.02]", o.is_archived && "opacity-55")}>
                    <td className={tdCls}>
                      <button type="button" className="text-left text-fg hover:text-cyan" onClick={() => setOpenId(o.id)}>
                        {o.name}
                      </button>
                      {o.aliases.length > 0 && <p className="text-[11.5px] text-fg-dim">aka {o.aliases.join(", ")}</p>}
                    </td>
                    <td className={cn(tdCls, "text-fg-muted")}>{o.email ?? o.phone ?? "—"}</td>
                    <td className={cn(tdCls, "font-mono text-[12px] text-fg-muted")}>{o.home_base_icao ?? "—"}</td>
                    <td className={tdCls}>
                      <Pill>{o.source === "extraction" ? "From a quote" : "Manual"}</Pill>
                      {o.is_archived && <Pill className="ml-1.5">Archived</Pill>}
                    </td>
                    <td className={cn(tdCls, "text-fg-dim")}>{fmtDate(o.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableScroll>
        )}
      </Panel>

      {creating && <OperatorForm onClose={() => setCreating(false)} onSaved={refresh} />}
      {openId && <OperatorDrawer id={openId} canEdit={canEdit} canArchive={canArchive} onClose={() => setOpenId(null)} onSaved={refresh} />}
    </div>
  );
}

function OperatorForm({ initial, onClose, onSaved }: { initial?: Operator; onClose: () => void; onSaved: () => void }) {
  const save = useMutation(async (data: FormData) => {
    const s = (k: string) => String(data.get(k) ?? "").trim() || null;
    const body = {
      name: s("name") ?? "",
      aliases: (s("aliases") ?? "").split(",").map((a) => a.trim()).filter(Boolean),
      email: s("email"),
      phone: s("phone"),
      website: s("website"),
      home_base_icao: s("home_base_icao")?.toUpperCase() ?? null,
      notes: s("notes"),
    };
    return initial ? endpoints.patchOperator(initial.id, body) : endpoints.createOperator(body);
  });

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (await save.run(new FormData(e.currentTarget))) {
      onSaved();
      onClose();
    }
  }

  return (
    <Dialog open onClose={onClose} title={initial ? `Edit ${initial.name}` : "Add operator"} wide>
      <form onSubmit={onSubmit} className="grid gap-4 sm:grid-cols-2">
        <Field label="Name" htmlFor="op-name" className="sm:col-span-2">
          <input id="op-name" name="name" required defaultValue={initial?.name} className={inputCls} />
        </Field>
        <Field label="Aliases" htmlFor="op-aliases" hint="Comma separated; used to match quotes.">
          <input id="op-aliases" name="aliases" defaultValue={initial?.aliases.join(", ")} className={inputCls} />
        </Field>
        <Field label="Home base (ICAO)" htmlFor="op-base">
          <input id="op-base" name="home_base_icao" defaultValue={initial?.home_base_icao ?? ""} className={cn(inputCls, "font-mono uppercase")} />
        </Field>
        <Field label="Email" htmlFor="op-email">
          <input id="op-email" name="email" type="email" defaultValue={initial?.email ?? ""} className={inputCls} />
        </Field>
        <Field label="Phone" htmlFor="op-phone">
          <input id="op-phone" name="phone" defaultValue={initial?.phone ?? ""} className={inputCls} />
        </Field>
        <Field label="Website" htmlFor="op-web" className="sm:col-span-2">
          <input id="op-web" name="website" defaultValue={initial?.website ?? ""} className={inputCls} />
        </Field>
        <Field label="Notes" htmlFor="op-notes" className="sm:col-span-2">
          <textarea id="op-notes" name="notes" defaultValue={initial?.notes ?? ""} className={textareaCls} />
        </Field>
        <InlineError error={save.error} className="sm:col-span-2" />
        <div className="flex justify-end gap-2 sm:col-span-2">
          <Btn tone="ghost" onClick={onClose}>Cancel</Btn>
          <Btn tone="primary" type="submit" pending={save.pending}>{initial ? "Save" : "Add operator"}</Btn>
        </div>
      </form>
    </Dialog>
  );
}

function OperatorDrawer({
  id,
  canEdit,
  canArchive,
  onClose,
  onSaved,
}: {
  id: string;
  canEdit: boolean;
  canArchive: boolean;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [rev, setRev] = useState(0);
  const op = useApi(`op:${id}`, () => endpoints.operator(id), rev);
  const [editing, setEditing] = useState(false);
  const archive = useMutation(() => endpoints.archiveOperator(id));
  const restore = useMutation(() => endpoints.patchOperator(id, { is_archived: false }));
  const o = op.data;

  if (editing && o)
    return (
      <OperatorForm
        initial={o}
        onClose={() => setEditing(false)}
        onSaved={() => {
          setRev((r) => r + 1);
          onSaved();
        }}
      />
    );

  return (
    <Dialog open onClose={onClose} title={o?.name ?? "Operator"} wide>
      {op.loading ? (
        <LoadingBlock rows={4} />
      ) : op.error && !o ? (
        <ErrorState error={op.error} onRetry={op.reload} />
      ) : o ? (
        <div className="flex flex-col gap-5">
          <ul className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              ["Quotes", o.stats.quote_count],
              ["Requested", o.stats.trips_requested],
              ["Quoted", o.stats.trips_quoted],
              ["Median reply", fmtHours(o.stats.median_response_hours)],
            ].map(([l, v]) => (
              <li key={l as string} className="surface-card rounded-xl p-3">
                <p className="font-mono text-[9.5px] uppercase tracking-[0.14em] text-fg-dim">{l}</p>
                <p className="tabular mt-1 text-lg font-semibold text-fg">{v}</p>
              </li>
            ))}
          </ul>
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-[13px]">
            <dt className="text-fg-dim">Email</dt>
            <dd className="text-fg">{o.email ?? "—"}</dd>
            <dt className="text-fg-dim">Phone</dt>
            <dd className="text-fg">{o.phone ?? "—"}</dd>
            <dt className="text-fg-dim">Website</dt>
            <dd className="break-all text-fg">{o.website ?? "—"}</dd>
            <dt className="text-fg-dim">Home base</dt>
            <dd className="font-mono text-fg">{o.home_base_icao ?? "—"}</dd>
            <dt className="text-fg-dim">Declined</dt>
            <dd className="text-fg">{o.stats.trips_declined}</dd>
            {o.notes && (
              <>
                <dt className="text-fg-dim">Notes</dt>
                <dd className="whitespace-pre-line text-fg-muted">{o.notes}</dd>
              </>
            )}
          </dl>
          <InlineError error={archive.error ?? restore.error} />
          <div className="flex flex-wrap justify-end gap-2">
            {canArchive &&
              (o.is_archived ? (
                <Btn pending={restore.pending} onClick={async () => { if (await restore.run()) { setRev((r) => r + 1); onSaved(); } }}>
                  Restore
                </Btn>
              ) : (
                <Btn tone="danger" pending={archive.pending} onClick={async () => { await archive.run(); onSaved(); onClose(); }}>
                  <Archive className="h-3.5 w-3.5" aria-hidden="true" /> Archive
                </Btn>
              ))}
            {canEdit && <Btn tone="primary" onClick={() => setEditing(true)}>Edit</Btn>}
          </div>
        </div>
      ) : null}
    </Dialog>
  );
}
