"use client";

import { useEffect, useMemo, useState } from "react";
import { Check, CheckCheck, ExternalLink, Flag as FlagIcon, Keyboard, Pencil } from "lucide-react";
import { endpoints, sourceFileUrl, type Flag, type ReviewItem } from "@/lib/api/endpoints";
import { useApi, useMutation } from "@/lib/api/hooks";
import { ApiError } from "@/lib/api/errors";
import { ConfidenceBadge } from "@/components/ui/confidence-badge";
import { cn } from "@/lib/utils";
import { useCan } from "../me-provider";
import { FieldEditor, Snippet, displayValue, fieldEditorInlineFields, highlightNeedle } from "../field-value";
import { FlagResolveDialog } from "../flag-resolve-dialog";
import { formatCents, humanize } from "../fmt";
import { SeverityIcon, SeverityPill } from "../status";
import { Btn, EmptyState, ErrorState, InlineError, LoadingBlock, Panel } from "../ui";
import { useTrip } from "./trip-context";

const BROKER_ONLY = "Broker review required";

function itemKey(i: ReviewItem) {
  return i.kind === "field" ? `f:${i.field?.id}` : `x:${i.flag?.id}`;
}

export function ReviewTab() {
  const { tripId, version, bump } = useTrip();
  const canReview = useCan("field.review");
  const canResolve = useCan("flag.resolve");
  const queue = useApi(`review:${tripId}`, () => endpoints.reviewQueue(tripId), version);
  const [selected, setSelected] = useState(0);
  const [editing, setEditing] = useState<string | null>(null);
  const [resolving, setResolving] = useState<{ flag: Flag; operator: string } | null>(null);
  const items = useMemo(() => queue.data?.items ?? [], [queue.data]);
  const sel = Math.min(selected, Math.max(0, items.length - 1));

  // Keyboard: j/k move, v verify, a accept, e edit.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable)) return;
      if (e.metaKey || e.ctrlKey || e.altKey || editing || resolving) return;
      if (e.key === "j") setSelected((s) => Math.min(items.length - 1, s + 1));
      else if (e.key === "k") setSelected((s) => Math.max(0, s - 1));
      else if (["v", "a", "e", "r"].includes(e.key)) {
        const item = items[sel];
        if (!item) return;
        document.getElementById(`review-${e.key}-${itemKey(item)}`)?.click();
      } else return;
      e.preventDefault();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [items, sel, editing, resolving]);

  useEffect(() => {
    const item = items[sel];
    if (item) document.getElementById(`review-item-${itemKey(item)}`)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [sel, items]);

  const done = () => {
    setEditing(null);
    bump();
  };

  const total = queue.data?.total ?? 0;
  const impact = items.reduce((s, i) => s + (i.money_impact_cents || 0), 0);

  return (
    <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1fr)_280px]">
      <Panel
        title="Review queue"
        sub={
          queue.data
            ? `${total} item${total === 1 ? "" : "s"} · ${formatCents(impact)} of charges depend on them · sorted by money impact`
            : "Low-confidence fields and blocking flags, sorted by money impact."
        }
        bodyClassName="p-0 sm:p-0"
      >
        {queue.loading ? (
          <div className="p-5">
            <LoadingBlock rows={4} label="Loading review queue" />
          </div>
        ) : queue.error && !queue.data ? (
          <div className="p-5">
            <ErrorState error={queue.error} onRetry={queue.reload} />
          </div>
        ) : items.length === 0 ? (
          <EmptyState
            icon={<CheckCheck className="h-5 w-5" strokeWidth={1.75} aria-hidden="true" />}
            title="Queue clear"
          >
            Every material field is above the review threshold or locked, and no blocking flags are open.
          </EmptyState>
        ) : (
          <ul className="divide-y divide-line">
            {items.map((item, i) => (
              <li
                key={itemKey(item)}
                id={`review-item-${itemKey(item)}`}
                onClick={() => setSelected(i)}
                className={cn(
                  "relative px-4 py-4 transition-colors sm:px-5",
                  i === sel ? "bg-white/[0.03]" : "hover:bg-white/[0.015]",
                )}
              >
                {i === sel && (
                  <span aria-hidden="true" className="absolute inset-y-3 left-0 w-[2px] rounded-full bg-cyan shadow-[0_0_10px_rgba(89,217,255,0.6)]" />
                )}
                {item.kind === "field" && item.field ? (
                  <FieldItem
                    item={item}
                    canReview={canReview}
                    editing={editing === item.field.id}
                    onEdit={() => setEditing(item.field!.id)}
                    onCancel={() => setEditing(null)}
                    onDone={done}
                    onConflict={queue.reload}
                  />
                ) : item.flag ? (
                  <FlagItem
                    item={item}
                    canResolve={canResolve}
                    onResolve={() => setResolving({ flag: item.flag!, operator: item.operator_name })}
                  />
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <aside className="flex flex-col gap-4">
        <Panel title="How review works">
          <ul className="flex flex-col gap-2.5 text-[12.5px] leading-relaxed text-fg-muted">
            <li>
              <span className="text-fg">Verify</span> confirms the extracted value against the source.
            </li>
            <li>
              <span className="text-fg">Accept</span> keeps a low-confidence value as-is, with a note.
            </li>
            <li>
              <span className="text-fg">Edit</span> replaces it. Every action locks the field and is audited.
            </li>
          </ul>
          {!canReview && (
            <p className="mt-3 rounded-lg border border-amber/25 bg-amber/[0.05] px-3 py-2 text-xs text-amber">
              {BROKER_ONLY}. Assistants can read the queue; a broker or admin clears it.
            </p>
          )}
        </Panel>
        <div className="hidden rounded-2xl border border-line p-4 text-xs text-fg-dim lg:block">
          <p className="mb-2 flex items-center gap-1.5 text-fg-muted">
            <Keyboard className="h-3.5 w-3.5" aria-hidden="true" /> Shortcuts
          </p>
          <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1">
            {[
              ["j / k", "next / previous"],
              ["v", "verify"],
              ["a", "accept"],
              ["e", "edit"],
              ["r", "resolve flag"],
            ].map(([k, d]) => (
              <div key={k} className="contents">
                <dt>
                  <kbd className="rounded border border-line px-1 font-mono text-[10.5px] text-fg-muted">{k}</kbd>
                </dt>
                <dd>{d}</dd>
              </div>
            ))}
          </dl>
        </div>
      </aside>

      <FlagResolveDialog
        flag={resolving?.flag ?? null}
        operatorName={resolving?.operator}
        onClose={() => setResolving(null)}
        onResolved={bump}
      />
    </div>
  );
}

function SourceLink({ item }: { item: ReviewItem }) {
  const f = item.field;
  const docId = f?.source_document_id ?? item.source?.document_id ?? item.flag?.source_document_id;
  if (!docId) return null;
  const page = f?.page ?? item.source?.page ?? null;
  const name = item.source?.original_filename ?? (item.source ? humanize(item.source.channel) : "source");
  return (
    <a
      href={sourceFileUrl(docId, page)}
      target="_blank"
      rel="noreferrer"
      onClick={(e) => e.stopPropagation()}
      className="inline-flex items-center gap-1 font-mono text-[11px] text-fg-dim hover:text-cyan"
    >
      {page ? `p.${page} · ` : ""}
      {name}
      <ExternalLink className="h-3 w-3" aria-hidden="true" />
    </a>
  );
}

function FieldItem({
  item,
  canReview,
  editing,
  onEdit,
  onCancel,
  onDone,
  onConflict,
}: {
  item: ReviewItem;
  canReview: boolean;
  editing: boolean;
  onEdit: () => void;
  onCancel: () => void;
  onDone: () => void;
  onConflict: () => void;
}) {
  const f = item.field!;
  const key = itemKey(item);
  const verify = useMutation(() => endpoints.verifyField(f.id, f.version));
  const accept = useMutation(() => endpoints.acceptField(f.id, f.version, null));
  const edit = useMutation((value: unknown, note: string | null) => endpoints.editField(f.id, f.version, value, note));
  const err = verify.error ?? accept.error ?? edit.error;
  const conflict = err instanceof ApiError && err.status === 409;

  async function run(p: Promise<unknown>) {
    if (await p) onDone();
  }

  return (
    <div className="flex flex-col gap-2.5">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-[11.5px] text-fg-dim">
            {item.operator_name}
          </p>
          <p className="mt-0.5 text-[14px] font-medium text-fg">{f.label ?? humanize(f.key)}</p>
        </div>
        <div className="flex items-center gap-2">
          {item.money_impact_cents > 0 && (
            <span className="tabular font-mono text-[11px] text-fg-dim">{formatCents(item.money_impact_cents)} at stake</span>
          )}
          <ConfidenceBadge value={f.confidence} />
        </div>
      </div>

      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="tabular font-mono text-[18px] font-semibold tracking-[-0.01em] text-amber">
          {displayValue(f, f.current_value)}
        </span>
        <SourceLink item={item} />
        {!f.snippet_verified && f.snippet && (
          <span className="text-[11px] text-fg-dim">snippet not found verbatim in source</span>
        )}
      </div>

      {f.snippet && <Snippet text={f.snippet} needles={highlightNeedle(f, f.current_value)} />}

      {editing ? (
        <FieldEditor field={f} pending={edit.pending} error={edit.error} onCancel={onCancel} onSubmit={(v, n) => run(edit.run(v, n))} />
      ) : (
        <div className="flex flex-wrap items-center gap-2" title={canReview ? undefined : BROKER_ONLY}>
          <Btn
            tone="primary"
            size="sm"
            disabled={!canReview}
            pending={verify.pending}
            onClick={() => run(verify.run())}
            aria-keyshortcuts="v"
          >
            <Check className="h-3.5 w-3.5" aria-hidden="true" /> Verify
          </Btn>
          <Btn size="sm" disabled={!canReview} pending={accept.pending} onClick={() => run(accept.run())} aria-keyshortcuts="a">
            Accept
          </Btn>
          <Btn size="sm" tone="ghost" disabled={!canReview} onClick={onEdit} aria-keyshortcuts="e">
            <Pencil className="h-3.5 w-3.5" aria-hidden="true" /> Edit
          </Btn>
          {!canReview && <span className="text-[11px] text-fg-dim">{BROKER_ONLY}</span>}
          <ShortcutTargets
            itemKey={key}
            enabled={canReview}
            onVerify={() => run(verify.run())}
            onAccept={() => run(accept.run())}
            onEdit={onEdit}
          />
        </div>
      )}
      {err && (
        <div className="flex flex-wrap items-center gap-2">
          <InlineError error={err} shownInline={editing && err === edit.error ? fieldEditorInlineFields(f) : []} />
          {conflict && (
            <Btn size="xs" onClick={onConflict}>
              Reload latest
            </Btn>
          )}
        </div>
      )}
    </div>
  );
}

/** Invisible buttons the j/k/v/a/e handler clicks, so shortcuts share the exact button logic. */
function ShortcutTargets({
  itemKey: key,
  enabled,
  onVerify,
  onAccept,
  onEdit,
}: {
  itemKey: string;
  enabled: boolean;
  onVerify: () => void;
  onAccept: () => void;
  onEdit: () => void;
}) {
  return (
    <span hidden>
      <button type="button" tabIndex={-1} id={`review-v-${key}`} disabled={!enabled} onClick={onVerify} />
      <button type="button" tabIndex={-1} id={`review-a-${key}`} disabled={!enabled} onClick={onAccept} />
      <button type="button" tabIndex={-1} id={`review-e-${key}`} disabled={!enabled} onClick={onEdit} />
    </span>
  );
}

function FlagItem({
  item,
  canResolve,
  onResolve,
}: {
  item: ReviewItem;
  canResolve: boolean;
  onResolve: () => void;
}) {
  const f = item.flag!;
  const key = itemKey(item);
  return (
    <div className="flex flex-col gap-2.5">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex min-w-0 items-start gap-2.5">
          <SeverityIcon severity={f.severity} className="mt-0.5" />
          <div className="min-w-0">
            <p className="text-[11.5px] text-fg-dim">{item.operator_name}</p>
            <p className="mt-0.5 text-[14px] font-medium text-fg">{humanize(f.type)}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {item.money_impact_cents > 0 && (
            <span className="tabular font-mono text-[11px] text-fg-dim">{formatCents(item.money_impact_cents)} at stake</span>
          )}
          <SeverityPill severity={f.severity} blocking={f.blocking} />
        </div>
      </div>
      <p className="text-[13px] leading-relaxed text-fg-muted">{f.message}</p>
      <SourceLink item={item} />
      <div className="flex flex-wrap items-center gap-2" title={canResolve ? undefined : BROKER_ONLY}>
        <Btn tone="amber" size="sm" disabled={!canResolve} onClick={onResolve} aria-keyshortcuts="r">
          <FlagIcon className="h-3.5 w-3.5" aria-hidden="true" /> Resolve
        </Btn>
        {!canResolve && <span className="text-[11px] text-fg-dim">{BROKER_ONLY}</span>}
        <span hidden>
          <button type="button" tabIndex={-1} id={`review-r-${key}`} disabled={!canResolve} onClick={onResolve} />
        </span>
      </div>
    </div>
  );
}

