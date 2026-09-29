"use client";

import { Fragment, useState } from "react";
import { ChevronRight } from "lucide-react";
import type { AuditEvent } from "@/lib/api/endpoints";
import { cn } from "@/lib/utils";
import { fmtDateTime } from "./fmt";

type Json = Record<string, unknown> | null;

function fmt(v: unknown): string {
  if (v === undefined) return "";
  if (typeof v === "string") return v;
  return JSON.stringify(v);
}

/** Key-level before/after diff; unchanged keys are omitted. */
export function JsonDiff({ before, after }: { before: Json; after: Json }) {
  const keys = [...new Set([...Object.keys(before ?? {}), ...Object.keys(after ?? {})])].sort();
  const changed = keys.filter((k) => fmt(before?.[k]) !== fmt(after?.[k]));
  if (!changed.length) return <p className="text-xs text-fg-dim">No field-level changes recorded.</p>;
  return (
    <dl className="grid grid-cols-[minmax(90px,auto)_1fr] gap-x-4 gap-y-1.5 font-mono text-[11.5px]">
      {changed.map((k) => (
        <Fragment key={k}>
          <dt className="truncate text-fg-dim">{k}</dt>
          <dd className="min-w-0 break-all">
            {before && k in before && <span className="mr-2 rounded bg-red-400/10 px-1 text-red-300 line-through decoration-red-300/50">{fmt(before[k])}</span>}
            {after && k in after && <span className="rounded bg-green/10 px-1 text-green">{fmt(after[k])}</span>}
          </dd>
        </Fragment>
      ))}
    </dl>
  );
}

export function AuditTable({ events, compact }: { events: AuditEvent[]; compact?: boolean }) {
  const [open, setOpen] = useState<string | null>(null);
  if (!events.length) return <p className="px-5 py-8 text-center text-sm text-fg-dim">No audit events.</p>;
  return (
    <ul className="divide-y divide-line">
      {events.map((e) => {
        const isOpen = open === e.id;
        const hasDiff = !!(e.before || e.after);
        return (
          <li key={e.id}>
            <button
              type="button"
              onClick={() => hasDiff && setOpen(isOpen ? null : e.id)}
              aria-expanded={hasDiff ? isOpen : undefined}
              className={cn(
                "flex w-full items-start gap-3 px-4 py-3 text-left sm:px-5",
                hasDiff ? "hover:bg-white/[0.02]" : "cursor-default",
              )}
            >
              <ChevronRight
                className={cn("mt-0.5 h-3.5 w-3.5 shrink-0 text-fg-dim transition-transform", isOpen && "rotate-90", !hasDiff && "opacity-0")}
                aria-hidden="true"
              />
              <span className="min-w-0 flex-1">
                <span className="flex flex-wrap items-baseline gap-x-2">
                  <span className="font-mono text-[12px] text-cyan">{e.action}</span>
                  <span className="text-[12px] text-fg-muted">{e.entity_type}</span>
                </span>
                <span className="mt-0.5 block text-[11.5px] text-fg-dim">
                  {e.actor_label ?? e.actor_kind} · {fmtDateTime(e.created_at)}
                  {!compact && e.ip ? ` · ${e.ip}` : ""}
                </span>
              </span>
            </button>
            {isOpen && (
              <div className="px-4 pb-4 pl-10 sm:px-5 sm:pl-11">
                <JsonDiff before={e.before ?? null} after={e.after ?? null} />
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
