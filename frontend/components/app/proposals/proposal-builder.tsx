"use client";

import { useState } from "react";
import Link from "next/link";
import {
  ArrowDown,
  ArrowUp,
  Ban,
  Check,
  Copy,
  ExternalLink,
  Link2Off,
  RefreshCw,
  Send,
  Undo2,
} from "lucide-react";
import { fieldErrorOf } from "@/lib/api/errors";
import {
  endpoints,
  type Proposal,
  type ProposalOption,
  type PublicProposal,
  type QuoteSummary,
} from "@/lib/api/endpoints";
import { useApi, useMutation } from "@/lib/api/hooks";
import { ConfidenceBadge } from "@/components/ui/confidence-badge";
import { ClientProposal } from "@/components/proposal/client-proposal";
import { cn } from "@/lib/utils";
import { useCan } from "../me-provider";
import { categoryLabel, fmtDateTime, formatCents, humanize } from "../fmt";
import { ProposalStatusPill } from "../status";
import {
  Btn,
  ErrorState,
  Field,
  FieldMessage,
  InlineError,
  LoadingBlock,
  Panel,
  Pill,
  Segmented,
  TableScroll,
  inputCls,
  selectCls,
  textareaCls,
} from "../ui";

type Draft = {
  quoteIds: string[];
  markup: string;
  title: string;
  clientName: string;
  message: string;
};

function draftFrom(p: Proposal): Draft {
  return {
    quoteIds: [...p.options].sort((a, b) => a.sort_order - b.sort_order).map((o) => o.quote_id),
    markup: String(p.markup_pct),
    title: p.title,
    clientName: p.client_name ?? "",
    message: p.message ?? "",
  };
}

/** Whole-dollar markup, as the backend computes it (spec §6). */
function clientTotal(costBasis: number, markupPct: number): number {
  const dollars = (costBasis / 100) * (1 + markupPct / 100);
  return Math.round(dollars) * 100;
}

function absoluteShareUrl(url: string | null): string | null {
  if (!url) return null;
  if (/^https?:\/\//.test(url)) return url;
  return typeof window === "undefined" ? url : `${window.location.origin}${url.startsWith("/") ? "" : "/"}${url}`;
}

export function ProposalBuilder({
  proposalId,
  onChanged,
  onOpen,
}: {
  proposalId: string;
  onChanged?: () => void;
  /** Called when an action creates a new proposal (revise). */
  onOpen?: (id: string) => void;
}) {
  const canManage = useCan("proposal.manage");
  const [rev, setRev] = useState(0);
  const proposal = useApi(`proposal:${proposalId}`, () => endpoints.proposal(proposalId), rev);
  const tripId = proposal.data?.trip_id;
  const quotes = useApi(tripId ? `quotes:${tripId}` : null, () => endpoints.quotes(tripId!), rev);
  const preview = useApi(`preview:${proposalId}`, () => endpoints.clientPreview(proposalId), rev);
  const [view, setView] = useState<"client" | "broker">("client");
  const [draft, setDraft] = useState<Draft | null>(null);
  const [draftFor, setDraftFor] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [choice, setChoice] = useState<string>("");

  // Reset the local draft whenever a new version of the proposal arrives.
  const p = proposal.data;
  const stamp = p ? `${p.id}:${p.updated_at}` : null;
  if (p && stamp !== draftFor) {
    setDraftFor(stamp);
    setDraft(draftFrom(p));
  }

  const refresh = () => {
    setRev((r) => r + 1);
    onChanged?.();
  };

  const save = useMutation((d: Draft) =>
    endpoints.patchProposal(proposalId, {
      options: d.quoteIds.map((quote_id) => ({ quote_id })),
      markup_pct: d.markup === "" ? null : d.markup,
      title: d.title || null,
      client_name: d.clientName || null,
      message: d.message || null,
    }),
  );
  const action = useMutation(
    (a: "send" | "rotate-link" | "revoke-link" | "decline" | "cancel" | "revise") => endpoints.proposalAction(proposalId, a),
  );
  const choose = useMutation((a: "mark-accepted" | "mark-booked", id: string | null) =>
    endpoints.proposalChoice(proposalId, a, id),
  );

  if (proposal.loading) return <Panel><LoadingBlock rows={6} label="Loading proposal" /></Panel>;
  if (proposal.error && !p) return <ErrorState error={proposal.error} onRetry={proposal.reload} />;
  if (!p || !draft) return null;

  const isDraft = p.status === "draft";
  const editable = isDraft && canManage;
  const markupNum = Number(draft.markup);
  const markupValid = draft.markup !== "" && Number.isFinite(markupNum) && markupNum >= 0 && markupNum <= 50;
  const dirty = JSON.stringify(draft) !== JSON.stringify(draftFrom(p));
  const shareUrl = absoluteShareUrl(p.share_url);
  const optionsSorted = [...p.options].sort((a, b) => a.sort_order - b.sort_order);
  const selectedOption = choice || p.accepted_option_id || optionsSorted.find((o) => o.is_recommended)?.id || optionsSorted[0]?.id || "";
  const err = save.error ?? action.error ?? choose.error;
  const fe = (name: string) => fieldErrorOf(err, name);
  // Per-quote eligibility failures come back keyed by quote id.
  const inlineFields = ["markup_pct", "title", "client_name", "message", "options", ...draft.quoteIds];

  async function doAction(a: Parameters<typeof action.run>[0]) {
    const res = await action.run(a);
    if (!res) return;
    if (a === "revise" && res.id !== proposalId) {
      onChanged?.();
      onOpen?.(res.id);
      return;
    }
    refresh();
  }

  async function doSave() {
    if (!draft) return false;
    const res = await save.run(draft);
    if (res) refresh();
    return !!res;
  }

  async function copy() {
    if (!shareUrl) return;
    try {
      await navigator.clipboard.writeText(shareUrl);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      window.prompt("Copy the client link", shareUrl);
    }
  }

  return (
    <div className="flex flex-col gap-5">
      {/* Header + lifecycle actions */}
      <div className="flex flex-col gap-3 rounded-2xl border border-line bg-white/[0.015] p-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <ProposalStatusPill status={p.status} />
            <span className="truncate text-[14px] font-medium text-fg">{p.title}</span>
          </div>
          <p className="mt-1 text-xs text-fg-dim">
            {p.trip_reference} · {p.options.length} option{p.options.length === 1 ? "" : "s"} · markup {p.markup_pct}%
            {p.sent_at && ` · sent ${fmtDateTime(p.sent_at)}`}
            {p.view_count > 0 && ` · viewed ${p.view_count}×`}
            {p.accepted_by_name && ` · accepted by ${p.accepted_by_name}`}
          </p>
        </div>
        {canManage && (
          <div className="flex flex-wrap items-center gap-2">
            {isDraft && (
              <>
                <Btn tone="ghost" onClick={() => doAction("cancel")}>
                  <Ban className="h-3.5 w-3.5" aria-hidden="true" /> Cancel draft
                </Btn>
                <Btn onClick={doSave} disabled={!dirty || !markupValid} pending={save.pending}>
                  Save
                </Btn>
                <Btn
                  tone="primary"
                  pending={action.pending}
                  disabled={!markupValid || draft.quoteIds.length === 0}
                  onClick={async () => {
                    if (dirty && !(await doSave())) return;
                    await doAction("send");
                  }}
                >
                  <Send className="h-3.5 w-3.5" aria-hidden="true" /> Send to client
                </Btn>
              </>
            )}
            {(p.status === "sent" || p.status === "accepted") && (
              <>
                <select
                  aria-label="Option"
                  value={selectedOption}
                  onChange={(e) => setChoice(e.target.value)}
                  className={cn(selectCls, "h-8 w-auto max-w-[200px] text-[12.5px]")}
                >
                  {optionsSorted.map((o) => (
                    <option key={o.id} value={o.id}>
                      {o.operator_name} · {formatCents(o.client_total_cents)}
                    </option>
                  ))}
                </select>
                {p.status === "sent" && (
                  <Btn onClick={async () => (await choose.run("mark-accepted", selectedOption)) && refresh()} pending={choose.pending}>
                    <Check className="h-3.5 w-3.5" aria-hidden="true" /> Mark accepted
                  </Btn>
                )}
                <Btn tone="primary" onClick={async () => (await choose.run("mark-booked", selectedOption)) && refresh()} pending={choose.pending}>
                  Mark booked
                </Btn>
              </>
            )}
            {p.status === "sent" && (
              <Btn tone="ghost" onClick={() => doAction("decline")}>
                Declined
              </Btn>
            )}
            {(p.status === "sent" || p.status === "accepted") && (
              <Btn tone="ghost" onClick={() => doAction("cancel")}>
                <Ban className="h-3.5 w-3.5" aria-hidden="true" /> Cancel
              </Btn>
            )}
            {!isDraft && p.status !== "superseded" && p.status !== "booked" && (
              <Btn onClick={() => doAction("revise")} pending={action.pending}>
                <Undo2 className="h-3.5 w-3.5" aria-hidden="true" /> Revise
              </Btn>
            )}
          </div>
        )}
      </div>

      {shareUrl && (
        <div className="flex flex-col gap-2 rounded-2xl border border-cyan/25 bg-cyan/[0.04] p-4 sm:flex-row sm:items-center">
          <div className="min-w-0 flex-1">
            <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-fg-dim">
              Client link {p.share_enabled ? "" : "· revoked"}
              {p.share_expires_at && p.share_enabled ? ` · expires ${fmtDateTime(p.share_expires_at)}` : ""}
            </p>
            <p className={cn("mt-1 truncate font-mono text-[12.5px]", p.share_enabled ? "text-ice" : "text-fg-dim line-through")} data-testid="share-url">
              {shareUrl}
            </p>
          </div>
          {p.share_enabled && (
            <div className="flex flex-wrap gap-2">
              <Btn onClick={copy}>
                {copied ? <Check className="h-3.5 w-3.5 text-green" aria-hidden="true" /> : <Copy className="h-3.5 w-3.5" aria-hidden="true" />}
                {copied ? "Copied" : "Copy link"}
              </Btn>
              <a
                href={shareUrl}
                target="_blank"
                rel="noreferrer"
                className="inline-flex h-8 items-center gap-1.5 rounded-full border border-line-strong px-3 text-[12.5px] text-fg hover:bg-white/[0.06]"
              >
                <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" /> Open
              </a>
              {canManage && (
                <>
                  <Btn tone="ghost" onClick={() => doAction("rotate-link")} title="Issue a new link; the old one stops working">
                    <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" /> Rotate
                  </Btn>
                  <Btn tone="ghost" onClick={() => doAction("revoke-link")}>
                    <Link2Off className="h-3.5 w-3.5" aria-hidden="true" /> Revoke
                  </Btn>
                </>
              )}
            </div>
          )}
        </div>
      )}
      {err && <InlineError error={err} shownInline={inlineFields} />}

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-[380px_minmax(0,1fr)]">
        {/* Left: options, markup, text */}
        <div className="flex min-w-0 flex-col gap-5">
          <Panel title="Options" sub={editable ? "Tick quotes to include; order sets the client's view." : "Frozen at send."}>
            <OptionPicker
              quotes={quotes.data?.items}
              loading={quotes.loading}
              selected={draft.quoteIds}
              editable={editable}
              onChange={(ids) => setDraft({ ...draft, quoteIds: ids })}
              errorFor={fe}
            />
            <FieldMessage className="mt-2">{fe("options")}</FieldMessage>
          </Panel>
          <Panel title="Pricing & message">
            <div className="flex flex-col gap-4">
              <Field
                label="Markup %"
                htmlFor="markup"
                error={fe("markup_pct")}
                hint="Applied to each option's known true cost. Only brokers see it."
              >
                <div className="flex items-center gap-3">
                  <input
                    type="range"
                    min={0}
                    max={25}
                    step={0.5}
                    value={markupValid ? markupNum : 0}
                    disabled={!editable}
                    onChange={(e) => setDraft({ ...draft, markup: e.target.value })}
                    aria-label="Markup slider"
                    className="flex-1 accent-[#59d9ff]"
                  />
                  <input
                    id="markup"
                    inputMode="decimal"
                    value={draft.markup}
                    disabled={!editable}
                    onChange={(e) => setDraft({ ...draft, markup: e.target.value })}
                    className={cn(inputCls, "tabular w-20 text-right font-mono", !markupValid && "border-amber/50")}
                  />
                </div>
              </Field>
              <Field label="Title" htmlFor="p-title" error={fe("title")}>
                <input id="p-title" value={draft.title} disabled={!editable} onChange={(e) => setDraft({ ...draft, title: e.target.value })} className={inputCls} />
              </Field>
              <Field label="Prepared for" htmlFor="p-client" error={fe("client_name")}>
                <input id="p-client" value={draft.clientName} disabled={!editable} onChange={(e) => setDraft({ ...draft, clientName: e.target.value })} className={inputCls} />
              </Field>
              <Field label="Message to client" htmlFor="p-msg" error={fe("message")}>
                <textarea id="p-msg" value={draft.message} disabled={!editable} onChange={(e) => setDraft({ ...draft, message: e.target.value })} className={textareaCls} />
              </Field>
            </div>
          </Panel>
        </div>

        {/* Right: preview */}
        <div className="min-w-0">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <Segmented
              label="Preview"
              value={view}
              onChange={setView}
              options={[
                { value: "client", label: "Client view" },
                { value: "broker", label: "Broker view" },
              ]}
            />
            {dirty && <Pill tone="amber">Unsaved changes: preview shows the saved version</Pill>}
          </div>
          <div className="relative overflow-hidden rounded-3xl border border-line bg-[linear-gradient(180deg,#111925_0%,#0b0f16_100%)] p-5 shadow-shell sm:p-8">
            <div
              aria-hidden="true"
              className="pointer-events-none absolute -top-40 left-1/2 h-80 w-[640px] max-w-full -translate-x-1/2 rounded-full bg-[radial-gradient(circle,rgba(91,140,255,0.14),transparent_65%)] blur-2xl"
            />
            <div className="relative">
              {view === "client" ? (
                <ClientPreview data={preview.data} loading={preview.loading} error={preview.error} retry={preview.reload} />
              ) : (
                <BrokerTable proposal={p} markup={markupValid && dirty ? markupNum : null} />
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function ClientPreview({
  data,
  loading,
  error,
  retry,
}: {
  data: PublicProposal | undefined;
  loading: boolean;
  error: Error | undefined;
  retry: () => void;
}) {
  if (loading) return <LoadingBlock rows={5} label="Loading client preview" />;
  if (error && !data) return <ErrorState error={error} onRetry={retry} />;
  if (!data) return null;
  return <ClientProposal proposal={data} />;
}

function OptionPicker({
  quotes,
  loading,
  selected,
  editable,
  onChange,
  errorFor,
}: {
  quotes: QuoteSummary[] | undefined;
  loading: boolean;
  selected: string[];
  editable: boolean;
  onChange: (ids: string[]) => void;
  /** The API's message for a quote id (e.g. why it can't go into a proposal). */
  errorFor: (quoteId: string) => string | null;
}) {
  if (loading || !quotes) return <LoadingBlock rows={3} />;
  const byId = new Map(quotes.map((q) => [q.id, q]));
  const ordered = [
    ...selected.map((id) => byId.get(id)).filter((q): q is QuoteSummary => !!q),
    ...quotes
      .filter((q) => !selected.includes(q.id) && q.status === "active")
      .sort((a, b) => Number(b.eligible_for_proposal) - Number(a.eligible_for_proposal)),
  ];
  if (!ordered.length) return <p className="text-sm text-fg-dim">No active quotes on this trip.</p>;

  function move(id: string, dir: -1 | 1) {
    const i = selected.indexOf(id);
    const j = i + dir;
    if (i < 0 || j < 0 || j >= selected.length) return;
    const next = [...selected];
    [next[i], next[j]] = [next[j], next[i]];
    onChange(next);
  }

  return (
    <ul className="flex flex-col gap-2">
      {ordered.map((q) => {
        const on = selected.includes(q.id);
        const blocked = !q.eligible_for_proposal;
        const idx = selected.indexOf(q.id);
        return (
          <li
            key={q.id}
            className={cn(
              "rounded-xl border px-3 py-2.5",
              on ? "border-cyan/30 bg-cyan/[0.04]" : "border-line",
              blocked && !on && "opacity-60",
            )}
          >
            <div className="flex items-center gap-3">
              <input
                type="checkbox"
                aria-label={`Include ${q.operator_name}`}
                checked={on}
                disabled={!editable || (blocked && !on)}
                onChange={() => onChange(on ? selected.filter((x) => x !== q.id) : [...selected, q.id])}
                className="h-4 w-4 accent-[#59d9ff]"
              />
              <div className="min-w-0 flex-1">
                <p className="truncate text-[13px] text-fg">
                  {q.operator_name}
                  {q.is_recommended && <span className="ml-2 font-mono text-[9.5px] tracking-[0.12em] text-cyan">RECOMMENDED</span>}
                </p>
                <p className="truncate text-[11.5px] text-fg-dim">
                  {q.aircraft_model ?? "—"} · {categoryLabel(q.aircraft_category)} ·{" "}
                  <span className="tabular font-mono text-fg-muted">
                    {formatCents(q.known_total_cents)}
                    {!q.is_fully_priced && <span className="text-amber">+</span>}
                  </span>
                </p>
              </div>
              {on && editable && (
                <span className="flex gap-0.5">
                  <button type="button" aria-label="Move up" disabled={idx === 0} onClick={() => move(q.id, -1)} className="grid h-7 w-7 place-items-center rounded-full text-fg-dim hover:bg-white/[0.06] hover:text-fg disabled:opacity-30">
                    <ArrowUp className="h-3.5 w-3.5" aria-hidden="true" />
                  </button>
                  <button type="button" aria-label="Move down" disabled={idx === selected.length - 1} onClick={() => move(q.id, 1)} className="grid h-7 w-7 place-items-center rounded-full text-fg-dim hover:bg-white/[0.06] hover:text-fg disabled:opacity-30">
                    <ArrowDown className="h-3.5 w-3.5" aria-hidden="true" />
                  </button>
                </span>
              )}
            </div>
            <FieldMessage className="mt-1.5 pl-7 text-[11.5px]">{errorFor(q.id)}</FieldMessage>
            {blocked && q.eligibility_reasons.length > 0 && (
              <ul className="mt-1.5 pl-7 text-[11.5px] text-amber">
                {q.eligibility_reasons.map((r) => (
                  <li key={r.code}>{r.message}</li>
                ))}
              </ul>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function BrokerTable({ proposal, markup }: { proposal: Proposal; markup: number | null }) {
  const opts = [...proposal.options].sort((a, b) => a.sort_order - b.sort_order);
  const total = (o: ProposalOption) => (markup == null ? o.client_total_cents : clientTotal(o.cost_basis_cents, markup));
  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2 font-mono text-[10.5px] tracking-[0.12em] text-fg-dim">
        <span>WORKSPACE · {proposal.trip_reference} · {opts.length} OPTIONS</span>
        <span>SOURCES VISIBLE · CONFIDENCE VISIBLE</span>
      </div>
      <TableScroll className="mt-5">
        <table className="w-full min-w-[860px] border-separate border-spacing-0 text-[12.5px]">
          <thead>
            <tr className="font-mono text-[10px] uppercase tracking-[0.14em] text-fg-dim">
              {["Operator", "Aircraft", "Headline", "Added", "True cost", "Markup", "Client total", "Confidence", "Sources"].map((h, i) => (
                <th key={h} className={cn("border-b border-line pb-2 pr-4 font-normal last:pr-0", i >= 2 && i <= 6 ? "text-right" : "text-left")}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {opts.map((o) => {
              const ct = total(o);
              return (
                <tr key={o.id} className={cn(!o.eligible && "text-amber")}>
                  <td className="border-b border-line py-3 pr-3 text-fg">
                    {o.operator_name}
                    {o.is_recommended && <span className="ml-2 font-mono text-[9.5px] tracking-[0.12em] text-cyan">REC</span>}
                  </td>
                  <td className="border-b border-line py-3 pr-3 text-fg-muted">{o.aircraft_model ?? "—"}</td>
                  <td className="tabular border-b border-line py-3 pr-3 text-right font-mono text-fg-muted">{formatCents(o.headline_cents)}</td>
                  <td className="tabular border-b border-line py-3 pr-3 text-right font-mono text-fg-muted" title={o.fee_lines.map((f) => `${f.label}: ${f.amount_cents != null ? formatCents(f.amount_cents) : humanize(f.amount_status)}`).join("\n")}>
                    {formatCents(o.added_charges_cents)}
                  </td>
                  <td className="tabular border-b border-line py-3 pr-3 text-right font-mono text-fg">{formatCents(o.cost_basis_cents)}</td>
                  <td className="tabular border-b border-line py-3 pr-3 text-right font-mono text-fg-muted">
                    {formatCents(ct - o.cost_basis_cents)}
                    <span className="ml-1 text-[10.5px] text-fg-dim">{markup ?? o.markup_pct_override ?? o.markup_pct}%</span>
                  </td>
                  <td className="tabular border-b border-line py-3 pr-4 text-right font-mono font-semibold text-ice">{formatCents(ct)}</td>
                  <td className="border-b border-line py-3 pr-4">
                    {o.quote_confidence != null ? <ConfidenceBadge value={o.quote_confidence} /> : "—"}
                  </td>
                  <td className="border-b border-line py-3 font-mono text-[11px] text-fg-dim">
                    {o.sources.map((s) => s.original_filename ?? humanize(s.channel)).join(", ") || "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </TableScroll>
      {opts.some((o) => !o.eligible) && (
        <ul className="mt-3 text-[12px] text-amber">
          {opts
            .filter((o) => !o.eligible)
            .map((o) => (
              <li key={o.id}>
                {o.operator_name}: {o.reasons.map((r) => r.message).join("; ")}
              </li>
            ))}
        </ul>
      )}
      <p className="mt-4 text-[12px] text-fg-dim">
        {markup != null
          ? "Markup preview reflects your unsaved change. Save to update the client view."
          : "Markup and sources never reach the client link."}{" "}
        <Link href={`/trips/${proposal.trip_id}?tab=quotes`} className="text-cyan hover:text-ice">
          Open comparison
        </Link>
      </p>
    </div>
  );
}
