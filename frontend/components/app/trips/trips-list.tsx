"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AlertTriangle, ArrowRight, Plus, PlaneTakeoff, Search } from "lucide-react";
import { endpoints, type TripStatus, type TripSummary } from "@/lib/api/endpoints";
import { useApi } from "@/lib/api/hooks";
import { cn } from "@/lib/utils";
import { useCan } from "../me-provider";
import { fmtLocal, formatCents } from "../fmt";

function RecTotal({ t }: { t: TripSummary }) {
  if (t.recommended_total_cents == null) return <>{formatCents(null)}</>;
  return (
    <>
      {formatCents(t.recommended_total_cents)}
      {t.is_fully_priced === false && (
        <span className="text-amber" aria-label="plus unconfirmed charges" title="Not fully priced">
          +
        </span>
      )}
    </>
  );
}
import { TripStatusPill } from "../status";
import { EmptyState, ErrorState, LoadingBlock, Panel, TableScroll, inputCls, tdCls, thCls } from "../ui";

const FILTERS: { value: "" | TripStatus; label: string }[] = [
  { value: "", label: "All" },
  { value: "sourcing", label: "Sourcing" },
  { value: "quoted", label: "Quoted" },
  { value: "proposed", label: "Proposed" },
  { value: "booked", label: "Booked" },
];

export function routeText(t: Pick<TripSummary, "legs">): string {
  if (!t.legs.length) return "—";
  const codes = [t.legs[0].origin_icao, ...t.legs.map((l) => l.destination_icao)];
  return codes.join(" → ");
}

export function TripsList() {
  const router = useRouter();
  const canWrite = useCan("trip.write");
  const [status, setStatus] = useState<"" | TripStatus>("");
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const trips = useApi(`trips:${status}:${query}`, () =>
    endpoints.trips({ status: status || undefined, q: query || undefined }),
  );

  return (
    <div className="mt-8 flex flex-col gap-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div role="tablist" aria-label="Trip status" className="flex flex-wrap gap-1.5">
          {FILTERS.map((f) => (
            <button
              key={f.value}
              type="button"
              role="tab"
              aria-selected={status === f.value}
              onClick={() => setStatus(f.value)}
              className={cn(
                "h-8 rounded-full border px-3 text-[12.5px] transition-colors",
                status === f.value
                  ? "border-cyan/35 bg-cyan/[0.08] text-ice"
                  : "border-line text-fg-muted hover:border-line-strong hover:text-fg",
              )}
            >
              {f.label}
            </button>
          ))}
        </div>
        <form
          role="search"
          onSubmit={(e) => {
            e.preventDefault();
            setQuery(q.trim());
          }}
          className="relative w-full sm:w-72"
        >
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-fg-dim" aria-hidden="true" />
          <input
            type="search"
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              if (!e.target.value) setQuery("");
            }}
            placeholder="Search reference, client, airport"
            aria-label="Search trips"
            className={cn(inputCls, "pl-9")}
          />
        </form>
      </div>

      <Panel bodyClassName="p-0 sm:p-0">
        {trips.loading ? (
          <div className="p-5">
            <LoadingBlock rows={5} label="Loading trips" />
          </div>
        ) : trips.error && !trips.data ? (
          <div className="p-5">
            <ErrorState error={trips.error} onRetry={trips.reload} />
          </div>
        ) : !trips.data?.items.length ? (
          <EmptyState
            icon={<PlaneTakeoff className="h-5 w-5" strokeWidth={1.75} aria-hidden="true" />}
            title={query || status ? "No trips match" : "No trips yet"}
            action={
              canWrite && !query && !status ? (
                <Link
                  href="/trips/new"
                  className="inline-flex h-9 items-center gap-1.5 rounded-full border border-cyan/30 bg-cyan/[0.08] px-4 text-[13px] text-ice hover:bg-cyan/[0.14]"
                >
                  <Plus className="h-4 w-4" aria-hidden="true" /> New trip
                </Link>
              ) : undefined
            }
          >
            {query || status
              ? "Try another filter or search term."
              : "Create a trip to start requesting quotes from operators."}
          </EmptyState>
        ) : (
          <>
            {/* Desktop table */}
            <TableScroll className="hidden px-5 pt-4 md:block">
              <table className="w-full min-w-[820px] border-separate border-spacing-0 text-[13px]">
                <thead>
                  <tr>
                    {["Reference", "Route", "Departure", "Pax", "Status", "Quotes", "Blocking", "Recommended"].map(
                      (h, i) => (
                        <th key={h} className={cn(thCls, i >= 3 && i !== 4 && "text-right")}>
                          {h}
                        </th>
                      ),
                    )}
                    <th className={thCls}>
                      <span className="sr-only">Open</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {trips.data.items.map((t) => (
                    <tr
                      key={t.id}
                      onClick={() => router.push(`/trips/${t.id}`)}
                      className="group cursor-pointer transition-colors hover:bg-white/[0.025]"
                    >
                      <td className={tdCls}>
                        <Link href={`/trips/${t.id}`} className="font-mono text-[12.5px] text-fg hover:text-cyan">
                          {t.reference}
                        </Link>
                        {t.client_name && <p className="mt-0.5 text-xs text-fg-dim">{t.client_name}</p>}
                      </td>
                      <td className={cn(tdCls, "font-mono text-[12px] text-fg-muted")}>{routeText(t)}</td>
                      <td className={cn(tdCls, "whitespace-nowrap text-fg-muted")}>
                        {fmtLocal(t.legs[0]?.depart_local, t.legs[0]?.depart_tz, true)}
                      </td>
                      <td className={cn(tdCls, "tabular text-right text-fg-muted")}>{t.pax}</td>
                      <td className={tdCls}>
                        <TripStatusPill status={t.status} />
                      </td>
                      <td className={cn(tdCls, "tabular text-right text-fg-muted")}>{t.quote_count ?? 0}</td>
                      <td className={cn(tdCls, "tabular text-right")}>
                        {t.open_blocking_flag_count > 0 ? (
                          <span
                            className="inline-flex items-center gap-1 text-amber"
                            title={`${t.open_blocking_flag_count} blocking · ${t.open_flag_count ?? 0} open`}
                          >
                            <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
                            {t.open_blocking_flag_count}
                          </span>
                        ) : (
                          <span className="text-fg-dim" title={`${t.open_flag_count ?? 0} open notes, none blocking`}>
                            0
                          </span>
                        )}
                      </td>
                      <td className={cn(tdCls, "tabular text-right font-mono text-fg")}>
                        <RecTotal t={t} />
                      </td>
                      <td className={cn(tdCls, "w-8 text-fg-dim")}>
                        <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5 group-hover:text-cyan" aria-hidden="true" />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableScroll>

            {/* Mobile cards */}
            <ul className="flex flex-col divide-y divide-line md:hidden">
              {trips.data.items.map((t) => (
                <li key={t.id}>
                  <Link href={`/trips/${t.id}`} className="flex flex-col gap-2 px-4 py-4 active:bg-white/[0.03]">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-[13px] text-fg">{t.reference}</span>
                      <TripStatusPill status={t.status} />
                    </div>
                    <p className="font-mono text-[12px] text-fg-muted">{routeText(t)}</p>
                    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-fg-dim">
                      <span>{fmtLocal(t.legs[0]?.depart_local, t.legs[0]?.depart_tz, true)}</span>
                      <span>{t.pax} pax</span>
                      <span>{t.quote_count ?? 0} quotes</span>
                      {t.open_blocking_flag_count > 0 && (
                        <span className="text-amber">{t.open_blocking_flag_count} blocking</span>
                      )}
                      {t.recommended_total_cents != null && (
                        <span className="tabular font-mono text-fg">
                          <RecTotal t={t} />
                        </span>
                      )}
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
            {trips.data.total > trips.data.items.length && (
              <p className="px-5 py-3 text-xs text-fg-dim">
                Showing {trips.data.items.length} of {trips.data.total}. Narrow with search.
              </p>
            )}
          </>
        )}
      </Panel>
    </div>
  );
}
