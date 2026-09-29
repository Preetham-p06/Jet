"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowLeft, Check, ExternalLink, History, Pencil, RotateCcw, Wifi, WifiOff } from "lucide-react";
import { endpoints, sourceFileUrl, type Field as FieldT, type Flag, type QuoteDetail } from "@/lib/api/endpoints";
import { useApi, useMutation } from "@/lib/api/hooks";
import { ApiError } from "@/lib/api/errors";
import { ConfidenceBadge } from "@/components/ui/confidence-badge";
import { cn } from "@/lib/utils";
import { useCan } from "../me-provider";
import { FieldEditor, Snippet, displayValue, fieldEditorInlineFields, highlightNeedle } from "../field-value";
import { FlagResolveDialog } from "../flag-resolve-dialog";
import { categoryLabel, fmtDateTime, fmtLocal, formatCents, formatDuration, formatMinor, humanize } from "../fmt";
import { SeverityIcon, SeverityPill } from "../status";
import { Btn, EmptyState, ErrorState, InlineError, LoadingBlock, Panel, Pill, RecommendedTag, TableScroll, tdCls, thCls } from "../ui";
import { TrueCostCell } from "../trips/comparison";
import { SignalBars } from "../trips/recommendation-tab";

export function QuoteDetailView({ tripId, quoteId }: { tripId: string; quoteId: string }) {
  const [rev, setRev] = useState(0);
  const quote = useApi(`quote:${quoteId}`, () => endpoints.quote(quoteId), rev);
  const bump = () => setRev((r) => r + 1);
  const canReview = useCan("field.review");
  const [resolving, setResolving] = useState<Flag | null>(null);
  const patch = useMutation((status: "active" | "withdrawn" | "rejected") => endpoints.patchQuote(quoteId, { status }));

  const back = (
    <Link href={`/trips/${tripId}?tab=quotes`} className="inline-flex items-center gap-1.5 text-xs text-fg-dim hover:text-fg">
      <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" /> Comparison
    </Link>
  );

  if (quote.loading)
    return (
      <div className="mx-auto w-full max-w-6xl">
        {back}
        <div className="mt-6"><LoadingBlock rows={8} label="Loading quote" /></div>
      </div>
    );
  if (quote.error && !quote.data) {
    const missing = quote.error instanceof ApiError && quote.error.status === 404;
    return (
      <div className="mx-auto w-full max-w-6xl">
        {back}
        <div className="mt-6">
          {missing ? <EmptyState title="Quote not found">It may have been merged or deleted.</EmptyState> : <ErrorState error={quote.error} onRetry={quote.reload} />}
        </div>
      </div>
    );
  }
  const q = quote.data!;
  const scalars = q.fields.filter((f) => f.group === "scalar" && f.is_current);
  const openFlags = q.flags.filter((f) => f.status === "open");

  return (
    <div className="mx-auto w-full max-w-6xl">
      {back}
      <header className="mt-3 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="eyebrow">Quote</p>
            {q.is_recommended && <RecommendedTag />}
            {q.status !== "active" && <Pill>{humanize(q.status)}</Pill>}
            {q.original_currency !== "USD" && <Pill tone="blue">{q.original_currency} → USD</Pill>}
          </div>
          <h1 className="mt-2 text-[26px] font-semibold leading-tight text-gradient-ice sm:text-3xl">{q.operator_name}</h1>
          <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-fg-muted">
            <span className="text-fg">{q.aircraft_model ?? "Aircraft TBC"}</span>
            {q.tail_number && <span className="font-mono text-fg-dim">{q.tail_number}</span>}
            <span>{categoryLabel(q.aircraft_category)}</span>
            {q.seats != null && <span>{q.seats} seats</span>}
            {q.wifi != null && (
              <span className="inline-flex items-center gap-1">
                {q.wifi ? <Wifi className="h-3.5 w-3.5" aria-hidden="true" /> : <WifiOff className="h-3.5 w-3.5" aria-hidden="true" />}
                {q.wifi ? "Wi-Fi" : "No Wi-Fi"}
              </span>
            )}
            {q.flight_time_minutes != null && <span>{formatDuration(q.flight_time_minutes)}</span>}
            {q.departure_local && <span>dep {fmtLocal(q.departure_local)}</span>}
            {q.availability && <span>{humanize(q.availability)}</span>}
          </p>
        </div>
        {canReview && (
          <div className="flex flex-wrap gap-2">
            {q.status === "active" ? (
              <>
                <Btn tone="ghost" pending={patch.pending} onClick={async () => (await patch.run("withdrawn")) && bump()}>
                  Mark withdrawn
                </Btn>
                <Btn tone="danger" pending={patch.pending} onClick={async () => (await patch.run("rejected")) && bump()}>
                  Reject
                </Btn>
              </>
            ) : (
              q.status !== "superseded" && (
                <Btn pending={patch.pending} onClick={async () => (await patch.run("active")) && bump()}>
                  Reactivate
                </Btn>
              )
            )}
          </div>
        )}
      </header>
      <InlineError error={patch.error} className="mt-2" />

      <ul className="mt-6 grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Stat label="Headline">{formatCents(q.headline_cents)}</Stat>
        <Stat label="True cost">
          <TrueCostCell known={q.known_total_cents} upper={q.upper_total_cents} fullyPriced={q.is_fully_priced} />
        </Stat>
        <Stat label="Upper bound">{formatCents(q.upper_total_cents)}</Stat>
        <Stat label="Quote confidence">
          {q.quote_confidence != null ? <ConfidenceBadge value={q.quote_confidence} size="md" /> : "—"}
        </Stat>
        <Stat label="Fit">{q.fit_score ?? "—"}</Stat>
      </ul>

      {!q.eligible_for_proposal && q.eligibility_reasons.length > 0 && (
        <div className="mt-4 rounded-xl border border-amber/25 bg-amber/[0.04] px-4 py-3 text-[12.5px] text-amber">
          <p className="font-medium">Not proposal-eligible yet</p>
          <ul className="mt-1 list-disc pl-5 text-amber/90">
            {q.eligibility_reasons.map((r) => (
              <li key={r.code}>{r.message}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-6 grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="flex min-w-0 flex-col gap-5">
          <FeeLinesPanel q={q} />
          <Panel title="Extracted fields" sub="Scalar values with their source evidence." bodyClassName="p-0 sm:p-0">
            {scalars.length === 0 ? (
              <p className="px-5 py-6 text-sm text-fg-dim">No fields extracted.</p>
            ) : (
              <ul className="divide-y divide-line">
                {scalars.map((f) => (
                  <FieldRow key={f.id} field={f} canReview={canReview} onChanged={bump} />
                ))}
              </ul>
            )}
          </Panel>
          <FeeFieldsPanel q={q} canReview={canReview} onChanged={bump} />
        </div>

        <div className="flex min-w-0 flex-col gap-5">
          <Panel title="Flags" sub={`${openFlags.length} open`} bodyClassName="p-0 sm:p-0">
            {q.flags.length === 0 ? (
              <p className="px-5 py-6 text-sm text-fg-dim">No flags.</p>
            ) : (
              <ul className="divide-y divide-line">
                {q.flags.map((f) => (
                  <li key={f.id} className={cn("flex gap-3 px-4 py-3", f.status !== "open" && "opacity-60")}>
                    <SeverityIcon severity={f.severity} className="mt-0.5" />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="text-[13px] text-fg">{humanize(f.type)}</span>
                        {f.status === "open" ? <SeverityPill severity={f.severity} blocking={f.blocking} /> : <Pill>{humanize(f.status)}</Pill>}
                      </div>
                      <p className="mt-1 text-[12px] leading-relaxed text-fg-muted">{f.message}</p>
                      {f.status === "open" && (
                        <Btn size="xs" className="mt-2" disabled={!canReview} title={canReview ? undefined : "Broker review required"} onClick={() => setResolving(f)}>
                          Resolve
                        </Btn>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Panel>

          {q.fit_breakdown && (
            <Panel title="Fit breakdown" actions={<span className="tabular font-mono text-xl font-semibold text-ice">{q.fit_breakdown.fit ?? "—"}</span>}>
              <SignalBars signals={q.fit_breakdown.signals} />
            </Panel>
          )}

          <Panel title="Sources" bodyClassName="p-0 sm:p-0">
            {q.sources.length === 0 ? (
              <p className="px-5 py-6 text-sm text-fg-dim">No sources.</p>
            ) : (
              <ul className="divide-y divide-line">
                {q.sources.map((s) => (
                  <li key={`${s.document_id}-${s.page ?? 0}`} className="px-4 py-3">
                    <a href={sourceFileUrl(s.document_id, s.page)} target="_blank" rel="noreferrer" className="inline-flex max-w-full items-center gap-1.5 truncate font-mono text-[12px] text-fg hover:text-cyan">
                      {s.original_filename ?? humanize(s.kind)}
                      <ExternalLink className="h-3 w-3 shrink-0 text-fg-dim" aria-hidden="true" />
                    </a>
                    <p className="text-[11.5px] text-fg-dim">
                      {humanize(s.channel)} · {fmtDateTime(s.received_at)}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </div>
      </div>

      <FlagResolveDialog flag={resolving} operatorName={q.operator_name} onClose={() => setResolving(null)} onResolved={bump} />
    </div>
  );
}

function Stat({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <li className="surface-card rounded-xl p-3.5">
      <p className="font-mono text-[9.5px] uppercase tracking-[0.14em] text-fg-dim">{label}</p>
      <div className="tabular mt-1.5 font-mono text-[18px] font-semibold text-fg">{children}</div>
    </li>
  );
}

function FeeLinesPanel({ q }: { q: QuoteDetail }) {
  const lines = [...q.fee_lines].sort((a, b) => a.sort_order - b.sort_order);
  return (
    <Panel title="True cost breakdown" sub="Every fee line after merging sources. Amber lines keep the quote from being fully priced." bodyClassName="p-0 sm:p-0">
      <TableScroll className="px-5 pt-3">
        <table className="w-full min-w-[620px] border-separate border-spacing-0 text-[13px]">
          <thead>
            <tr>
              <th className={thCls}>Charge</th>
              <th className={thCls}>Status</th>
              <th className={cn(thCls, "text-right")}>Amount</th>
              <th className={thCls}>Confidence</th>
              <th className={thCls}>Source</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td className={cn(tdCls, "text-fg")}>Headline {q.pricing_basis === "hourly" && <span className="text-xs text-fg-dim">(hourly)</span>}</td>
              <td className={tdCls} />
              <td className={cn(tdCls, "tabular text-right font-mono text-fg")}>{formatCents(q.headline_cents)}</td>
              <td className={tdCls} />
              <td className={tdCls} />
            </tr>
            {lines.map((l) => {
              const amber = !l.counts_in_known && l.counts_in_upper;
              return (
                <tr key={l.id} className={cn(!l.counts_in_known && !l.counts_in_upper && "text-fg-dim")}>
                  <td className={cn(tdCls, "text-fg")}>
                    {l.label}
                    {l.explicitly_extra && <span className="ml-1.5 text-[11px] text-fg-dim">extra</span>}
                    {l.estimate_basis && <p className="text-[11px] text-fg-dim">{l.estimate_basis}</p>}
                  </td>
                  <td className={tdCls}>
                    <span className={cn("text-[12px]", amber ? "text-amber" : "text-fg-muted")}>
                      {humanize(l.amount_status)}
                      {l.included_by === "all_in" && " (all-in)"}
                    </span>
                  </td>
                  <td className={cn(tdCls, "tabular text-right font-mono", amber ? "text-amber" : "text-fg")}>
                    {l.amount_cents != null
                      ? formatCents(l.amount_cents)
                      : l.estimate_cents != null
                        ? `≤ ${formatCents(l.estimate_cents)}`
                        : l.percent != null
                          ? `${l.percent}%`
                          : "—"}
                    {l.original_currency && l.original_currency !== "USD" && l.original_amount_minor != null && (
                      <p className="text-[10.5px] text-fg-dim">
                        {formatMinor(l.original_amount_minor, l.original_currency)}
                      </p>
                    )}
                  </td>
                  <td className={tdCls}>
                    {l.confidence != null ? <ConfidenceBadge value={l.confidence} verified={l.review_status === "verified" || l.review_status === "edited"} /> : null}
                  </td>
                  <td className={tdCls}>
                    {l.source_document_id && (
                      <a href={sourceFileUrl(l.source_document_id, l.page)} target="_blank" rel="noreferrer" className="font-mono text-[11px] text-fg-dim hover:text-cyan">
                        {l.page ? `p.${l.page}` : "open"}
                      </a>
                    )}
                  </td>
                </tr>
              );
            })}
            <tr>
              <td className={cn(tdCls, "font-medium text-ice")}>True cost</td>
              <td className={tdCls}>{!q.is_fully_priced && <span className="text-[12px] text-amber">Not fully priced</span>}</td>
              <td className={cn(tdCls, "text-right text-[14px]")}>
                <TrueCostCell known={q.known_total_cents} upper={q.upper_total_cents} fullyPriced={q.is_fully_priced} />
              </td>
              <td className={tdCls} />
              <td className={tdCls} />
            </tr>
          </tbody>
        </table>
      </TableScroll>
    </Panel>
  );
}

function FeeFieldsPanel({ q, canReview, onChanged }: { q: QuoteDetail; canReview: boolean; onChanged: () => void }) {
  const fees = q.fields.filter((f) => f.group === "fee" && f.is_current);
  if (!fees.length) return null;
  return (
    <Panel title="Fee evidence" sub="The extracted fee statements behind the breakdown." bodyClassName="p-0 sm:p-0">
      <ul className="divide-y divide-line">
        {fees.map((f) => (
          <FieldRow key={f.id} field={f} canReview={canReview} onChanged={onChanged} />
        ))}
      </ul>
    </Panel>
  );
}

function FieldRow({ field: f, canReview, onChanged }: { field: FieldT; canReview: boolean; onChanged: () => void }) {
  const [editing, setEditing] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const verify = useMutation(() => endpoints.verifyField(f.id, f.version));
  const reset = useMutation(() => endpoints.resetField(f.id, f.version));
  const edit = useMutation((v: unknown, note: string | null) => endpoints.editField(f.id, f.version, v, note));
  const history = useApi(showHistory ? `history:${f.id}` : null, () => endpoints.fieldHistory(f.id));
  const err = verify.error ?? reset.error ?? edit.error;
  const done = async (p: Promise<unknown>) => {
    if (await p) {
      setEditing(false);
      onChanged();
    }
  };

  return (
    <li className="px-4 py-3.5 sm:px-5">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-[11.5px] text-fg-dim">{f.label ?? humanize(f.key)}</p>
          <p className={cn("tabular mt-0.5 font-mono text-[14px]", f.status === "extracted" && f.confidence < 75 ? "text-amber" : "text-fg")}>
            {displayValue(f, f.current_value)}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {f.status !== "extracted" && <Pill tone={f.status === "verified" ? "green" : "cyan"}>{humanize(f.status)}</Pill>}
          <ConfidenceBadge value={f.confidence} verified={f.status === "verified"} />
          {f.source_document_id && (
            <a href={sourceFileUrl(f.source_document_id, f.page)} target="_blank" rel="noreferrer" className="font-mono text-[11px] text-fg-dim hover:text-cyan">
              {f.page ? `p.${f.page}` : "source"}
            </a>
          )}
        </div>
      </div>
      {f.snippet && <Snippet className="mt-2" text={f.snippet} needles={highlightNeedle(f, f.current_value)} />}
      {editing ? (
        <div className="mt-2">
          <FieldEditor field={f} pending={edit.pending} error={edit.error} onCancel={() => setEditing(false)} onSubmit={(v, n) => done(edit.run(v, n))} />
        </div>
      ) : (
        <div className="mt-2 flex flex-wrap gap-1.5" title={canReview ? undefined : "Broker review required"}>
          {f.status === "extracted" && (
            <Btn size="xs" disabled={!canReview} pending={verify.pending} onClick={() => done(verify.run())}>
              <Check className="h-3 w-3" aria-hidden="true" /> Verify
            </Btn>
          )}
          <Btn size="xs" tone="ghost" disabled={!canReview} onClick={() => setEditing(true)}>
            <Pencil className="h-3 w-3" aria-hidden="true" /> Edit
          </Btn>
          {f.status !== "extracted" && (
            <Btn size="xs" tone="ghost" disabled={!canReview} pending={reset.pending} onClick={() => done(reset.run())}>
              <RotateCcw className="h-3 w-3" aria-hidden="true" /> Reset
            </Btn>
          )}
          <Btn size="xs" tone="ghost" onClick={() => setShowHistory((s) => !s)} aria-label="Value history">
            <History className="h-3 w-3" aria-hidden="true" /> History
          </Btn>
        </div>
      )}
      <InlineError error={err} shownInline={editing && err === edit.error ? fieldEditorInlineFields(f) : []} className="mt-1.5" />
      {showHistory && (
        <div className="mt-2 rounded-lg border border-line p-2.5 text-[12px]">
          {history.loading ? (
            <p className="text-fg-dim">Loading…</p>
          ) : history.error ? (
            <InlineError error={history.error} />
          ) : !history.data?.items.length ? (
            <p className="text-fg-dim">No earlier values.</p>
          ) : (
            <ul className="flex flex-col gap-1">
              {history.data.items.map((h) => (
                <li key={h.id} className="flex flex-wrap justify-between gap-2 text-fg-muted">
                  <span className="font-mono">{displayValue(h, h.current_value)}</span>
                  <span className="text-fg-dim">
                    {humanize(h.status)} · {fmtDateTime(h.updated_at)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </li>
  );
}
