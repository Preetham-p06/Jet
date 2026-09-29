"use client";

import Link from "next/link";
import { AlertTriangle, Flag as FlagIcon, Wifi, WifiOff } from "lucide-react";
import type { Comparison, ComparisonCell, ComparisonRow, QuoteSummary } from "@/lib/api/endpoints";
import type { Quote as DemoQuote } from "@/lib/demo-data";
import { ConfidenceBadge } from "@/components/ui/confidence-badge";
import { QuoteCard } from "@/components/ui/quote-card";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { categoryLabel, formatCents, formatDuration, humanize } from "../fmt";
import { RecommendedTag, TableScroll } from "../ui";

/* ------------------------------------------------------------------ */
/* Cells                                                               */
/* ------------------------------------------------------------------ */

/** One fee category for one quote: amount, "Included", amber "est. $850" or "Not stated". */
export function FeeCell({ cell, threshold }: { cell: ComparisonCell | undefined; threshold: number }) {
  if (!cell || cell.amount_status == null) return <span className="text-fg-dim/60">—</span>;
  const lowConf = cell.confidence != null && cell.confidence < threshold && cell.review_status === "extracted";
  const multi = cell.line_count > 1 ? <span className="ml-1 text-[10px] text-fg-dim">×{cell.line_count}</span> : null;
  const src = cell.source
    ? `${cell.source.original_filename ?? humanize(cell.source.channel)}${cell.source.page ? ` · p.${cell.source.page}` : ""}`
    : null;

  switch (cell.amount_status) {
    case "included":
    case "waived":
      return (
        <span className="text-[12px] text-fg-muted" title={src ?? undefined}>
          {cell.amount_status === "waived" ? "Waived" : "Included"}
          {cell.included_by === "all_in" && <span className="ml-1 text-[10px] text-fg-dim">all-in</span>}
        </span>
      );
    case "not_applicable":
      return <span className="text-[12px] text-fg-dim">N/A</span>;
    case "not_stated":
      return (
        <span className="inline-flex flex-col items-end leading-tight">
          <span className="text-[12px] text-amber">Not stated</span>
          {cell.estimate_cents != null && (
            <span className="tabular font-mono text-[10.5px] text-amber/75">est. {formatCents(cell.estimate_cents)}</span>
          )}
        </span>
      );
    case "estimated": {
      const accepted = cell.review_status === "accepted" || cell.review_status === "verified" || cell.review_status === "edited";
      return (
        <span className={cn("tabular font-mono text-[12.5px]", accepted ? "text-fg" : "text-amber")} title={src ?? undefined}>
          <span className="mr-1 font-sans text-[10.5px]">est.</span>
          {formatCents(cell.amount_cents ?? cell.estimate_cents)}
          {multi}
        </span>
      );
    }
    default:
      return (
        <span className={cn("tabular font-mono text-[12.5px]", lowConf ? "text-amber" : "text-fg")} title={src ?? undefined}>
          {formatCents(cell.amount_cents)}
          {lowConf && <AlertTriangle className="ml-1 inline h-3 w-3 -translate-y-px" aria-label={`Confidence ${cell.confidence}%`} />}
          {multi}
        </span>
      );
  }
}

/** Known total, plus an amber "+" whose tooltip gives the upper bound when not fully priced. */
export function TrueCostCell({
  known,
  upper,
  fullyPriced,
  className,
}: {
  known: number | null;
  upper: number | null;
  fullyPriced: boolean;
  className?: string;
}) {
  if (known == null) return <span className="text-fg-dim">—</span>;
  if (fullyPriced) {
    return <span className={cn("tabular font-mono font-semibold text-fg", className)}>{formatCents(known)}</span>;
  }
  return (
    <Tooltip
      side="top"
      triggerClassName={cn("tabular font-mono font-semibold text-fg decoration-amber/60", className)}
      content={
        <>
          Not fully priced. Up to <span className="font-mono text-fg">{formatCents(upper)}</span> once unstated or
          estimated charges are confirmed.
        </>
      }
    >
      {formatCents(known)}
      <span className="text-amber" aria-label="plus unconfirmed charges">
        +
      </span>
    </Tooltip>
  );
}

function FitBadge({ q }: { q: QuoteSummary }) {
  if (q.fit_score == null) return <span className="text-fg-dim">—</span>;
  return (
    <span
      className={cn(
        "tabular inline-flex items-center gap-1 rounded-full border px-2 py-0.5 font-mono text-[11px]",
        q.is_recommended ? "border-cyan/35 bg-cyan/[0.08] text-cyan" : "border-line-strong bg-white/[0.03] text-fg-muted",
        !q.eligible_for_proposal && !q.is_recommended && "opacity-80",
      )}
      title={q.eligibility_reasons.map((r) => r.message).join("\n") || undefined}
    >
      <span className="text-fg-dim">fit</span> {q.fit_score}
    </span>
  );
}

/* ------------------------------------------------------------------ */
/* Table                                                               */
/* ------------------------------------------------------------------ */

const stickyCls = "sticky left-0 z-10 bg-[#0c1119]";
const th = "whitespace-nowrap border-b border-line px-3 pb-2.5 pt-1 font-mono text-[10px] font-normal uppercase tracking-[0.14em] text-fg-dim";
const td = "border-b border-line px-3 py-3 align-middle";

export function ComparisonTable({ data, tripId }: { data: Comparison; tripId: string }) {
  const threshold = data.review_threshold;
  const rows = data.rows;
  const recId = data.recommended_quote_id;

  return (
    <TableScroll>
      <table className="w-full border-separate border-spacing-0 text-[13px]" style={{ minWidth: 980 + data.fee_columns.length * 110 }}>
        <thead>
          <tr>
            <th className={cn(th, stickyCls, "pl-0 text-left")}>Operator</th>
            <th className={cn(th, "text-left")}>Aircraft</th>
            <th className={cn(th, "text-left")}>Category</th>
            <th className={cn(th, "text-right")}>Seats</th>
            <th className={cn(th, "text-center")}>Wi-Fi</th>
            <th className={cn(th, "text-right")}>Headline</th>
            {data.fee_columns.map((c) => (
              <th key={c.category} className={cn(th, "text-right")}>
                {c.label}
              </th>
            ))}
            <th className={cn(th, "text-right")}>Added</th>
            <th className={cn(th, "text-right text-ice")}>True cost</th>
            <th className={cn(th, "text-left")}>Confidence</th>
            <th className={cn(th, "text-left")}>Fit</th>
            <th className={cn(th, "pr-0 text-left")}>Flags</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const q = r.quote;
            const rec = q.id === recId || q.is_recommended;
            const inactive = q.status !== "active";
            const blocking = r.open_flags.filter((f) => f.blocking);
            return (
              <tr
                key={q.id}
                className={cn(
                  "group transition-colors hover:bg-white/[0.02]",
                  rec && "bg-cyan/[0.035]",
                  inactive && "opacity-55",
                )}
              >
                <td className={cn(td, stickyCls, "pl-0", rec && "shadow-[inset_2px_0_0_var(--color-cyan)]")}>
                  <div className="flex flex-col gap-1 pl-2">
                    <Link
                      href={`/trips/${tripId}/quotes/${q.id}`}
                      className="max-w-[180px] truncate font-medium text-fg hover:text-cyan"
                    >
                      {q.operator_name}
                    </Link>
                    <div className="flex flex-wrap items-center gap-1.5">
                      {rec && <RecommendedTag />}
                      {inactive && <span className="font-mono text-[10px] uppercase text-fg-dim">{q.status}</span>}
                    </div>
                  </div>
                </td>
                <td className={cn(td, "max-w-[190px] truncate text-fg-muted")} title={q.aircraft_model ?? undefined}>
                  {q.aircraft_model ?? "—"}
                </td>
                <td className={cn(td, "whitespace-nowrap text-fg-muted")}>{categoryLabel(q.aircraft_category)}</td>
                <td className={cn(td, "tabular text-right text-fg-muted")}>{q.seats ?? "—"}</td>
                <td className={cn(td, "text-center")}>
                  {q.wifi == null ? (
                    <span className="text-fg-dim">—</span>
                  ) : q.wifi ? (
                    <Wifi className="mx-auto h-3.5 w-3.5 text-fg-muted" aria-label="Wi-Fi" />
                  ) : (
                    <WifiOff className="mx-auto h-3.5 w-3.5 text-fg-dim" aria-label="No Wi-Fi" />
                  )}
                </td>
                <td className={cn(td, "tabular text-right font-mono text-fg-muted")}>{formatCents(q.headline_cents)}</td>
                {data.fee_columns.map((c) => (
                  <td key={c.category} className={cn(td, "text-right")}>
                    <FeeCell cell={r.fees.find((f) => f.category === c.category)} threshold={threshold} />
                  </td>
                ))}
                <td className={cn(td, "tabular text-right font-mono text-fg-muted")}>
                  {formatCents(r.added_charges_cents)}
                  {!q.is_fully_priced && r.added_charges_cents != null && <span className="text-amber">+</span>}
                </td>
                <td className={cn(td, "text-right text-[14px]")}>
                  <TrueCostCell known={q.known_total_cents} upper={q.upper_total_cents} fullyPriced={q.is_fully_priced} />
                </td>
                <td className={td}>
                  {q.quote_confidence != null ? <ConfidenceBadge value={q.quote_confidence} /> : <span className="text-fg-dim">—</span>}
                </td>
                <td className={td}>
                  <FitBadge q={q} />
                </td>
                <td className={cn(td, "pr-0")}>
                  {blocking.length ? (
                    <Link
                      href={`/trips/${tripId}?tab=flags`}
                      className="inline-flex items-center gap-1 text-amber hover:text-ice"
                      title={blocking.map((f) => f.message).join("\n")}
                    >
                      <FlagIcon className="h-3.5 w-3.5" aria-hidden="true" /> {blocking.length}
                    </Link>
                  ) : r.open_flags.length ? (
                    <span className="inline-flex items-center gap-1 text-fg-dim" title={r.open_flags.map((f) => f.message).join("\n")}>
                      <FlagIcon className="h-3.5 w-3.5" aria-hidden="true" /> {r.open_flags.length}
                    </span>
                  ) : (
                    <span className="text-fg-dim">—</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11.5px] text-fg-dim">
        <span>
          <span className="text-amber">Amber</span> values are estimated, unstated or below the {threshold}% review threshold.
        </span>
        <span>
          <span className="font-mono text-fg">$41,980</span>
          <span className="text-amber">+</span> means not fully priced; hover for the upper bound.
        </span>
      </p>
    </TableScroll>
  );
}

/* ------------------------------------------------------------------ */
/* Cards view: adapter to the landing page's QuoteCard                 */
/* ------------------------------------------------------------------ */

function toDemoQuote(r: ComparisonRow, labels: Map<string, string>): DemoQuote {
  const q = r.quote;
  const fees = r.fees
    .filter((f) => f.amount_status && f.amount_status !== "not_applicable")
    .map((f) => {
      const flagged = f.amount_status === "not_stated" || (f.amount_status === "estimated" && f.review_status === "extracted");
      const amount =
        f.amount_status === "included" || f.amount_status === "waived"
          ? null
          : f.amount_status === "not_stated"
            ? null
            : (f.amount_cents ?? f.estimate_cents ?? 0) / 100;
      return {
        label: labels.get(f.category) ?? humanize(f.category),
        amount,
        source: f.source?.original_filename ?? "",
        page: f.source?.page ?? undefined,
        confidence: f.confidence ?? 100,
        flagged,
      };
    });
  const blocking = r.open_flags.find((f) => f.blocking);
  return {
    id: q.id,
    operator: q.operator_name,
    aircraft: q.aircraft_model ?? "Aircraft TBC",
    category: categoryLabel(q.aircraft_category),
    headline: (q.headline_cents ?? 0) / 100,
    fees,
    trueCost: (q.known_total_cents ?? 0) / 100,
    fit: q.fit_score ?? 0,
    finalFit: q.fit_score ?? 0,
    seats: q.seats ?? 0,
    wifi: !!q.wifi,
    flightTime: formatDuration(q.flight_time_minutes),
    sourceFile: "",
    recommended: q.is_recommended,
    warning: blocking?.message ?? (q.is_fully_priced ? undefined : "Not fully priced"),
  };
}

export function ComparisonCards({ data }: { data: Comparison }) {
  const labels = new Map(data.fee_columns.map((c) => [c.category as string, c.label]));
  return (
    <ul className="grid gap-4 pt-3 sm:grid-cols-2 xl:grid-cols-4">
      {data.rows.map((r) => {
        const dq = toDemoQuote(r, labels);
        const rec = r.quote.id === data.recommended_quote_id || r.quote.is_recommended;
        return (
          <li key={r.quote.id}>
            <QuoteCard
              quote={dq}
              visible
              extracting={false}
              populated
              scored
              highlight={rec}
              warned={!rec && (!r.quote.is_fully_priced || r.open_flags.some((f) => f.blocking))}
            />
          </li>
        );
      })}
    </ul>
  );
}
