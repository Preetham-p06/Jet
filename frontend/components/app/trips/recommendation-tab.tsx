"use client";

import { useState } from "react";
import Link from "next/link";
import { Check, Sparkles, X } from "lucide-react";
import { endpoints, type RankingEntry, type Signal } from "@/lib/api/endpoints";
import { useApi } from "@/lib/api/hooks";
import { ConfidenceBadge } from "@/components/ui/confidence-badge";
import { cn } from "@/lib/utils";
import { fmtDateTime } from "../fmt";
import { EmptyState, ErrorState, LoadingBlock, Panel, RecommendedTag, TableScroll, tdCls, thCls } from "../ui";
import { TrueCostCell } from "./comparison";
import { useTrip } from "./trip-context";

export function SignalBars({ signals }: { signals: Signal[] }) {
  return (
    <ul className="flex flex-col gap-3">
      {signals.map((s) => {
        const v = s.value ?? 0;
        return (
          <li key={s.key} className={cn("grid grid-cols-[112px_1fr_44px] items-center gap-3 text-[12.5px]", s.dropped && "opacity-45")}>
            <span className="min-w-0">
              <span className="block truncate text-fg">{s.label}</span>
              <span className="font-mono text-[10px] text-fg-dim">
                w {s.weight}
                {s.imputed && " · neutral"}
                {s.dropped && " · dropped"}
              </span>
            </span>
            <span className="relative h-2 overflow-hidden rounded-full bg-white/[0.05]" title={s.detail ?? undefined}>
              <span
                className="block h-full rounded-full transition-[width] duration-700 ease-out-expo"
                style={{
                  width: `${Math.max(0, Math.min(100, v))}%`,
                  background: s.imputed
                    ? "repeating-linear-gradient(135deg,rgba(154,166,178,0.55) 0 4px,rgba(154,166,178,0.25) 4px 8px)"
                    : "#5B8CFF",
                }}
              />
            </span>
            <span className="tabular text-right font-mono text-[12px] text-fg">
              {s.dropped || s.value == null ? "—" : Math.round(v)}
            </span>
            {s.detail && <span className="col-span-3 -mt-1.5 pl-[124px] text-[11px] text-fg-dim max-sm:pl-0">{s.detail}</span>}
          </li>
        );
      })}
    </ul>
  );
}

export function RecommendationTab() {
  const { tripId, version } = useTrip();
  const rec = useApi(`rec:${tripId}`, () => endpoints.recommendation(tripId), version);
  const [picked, setPicked] = useState<string | null>(null);

  if (rec.loading) return <Panel><LoadingBlock rows={6} label="Loading recommendation" /></Panel>;
  if (rec.error && !rec.data) return <ErrorState error={rec.error} onRetry={rec.reload} />;
  const r = rec.data;
  if (!r || !r.ranking.length)
    return (
      <Panel>
        <EmptyState icon={<Sparkles className="h-5 w-5" strokeWidth={1.75} aria-hidden="true" />} title="No recommendation yet">
          Once quotes are extracted and normalized, JetStream scores each one and recommends the best eligible option.
        </EmptyState>
      </Panel>
    );

  const recommended = r.ranking.find((e) => e.quote_id === r.recommended_quote_id) ?? null;
  const focus: RankingEntry = r.ranking.find((e) => e.quote_id === picked) ?? recommended ?? r.ranking[0];
  const passed = r.checks.filter((c) => c.passed).length;

  return (
    <div className="flex flex-col gap-5">
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <Panel
          title={
            <span className="flex flex-wrap items-center gap-2">
              Fit breakdown · {focus.operator_name}
              {focus.quote_id === r.recommended_quote_id && <RecommendedTag />}
            </span>
          }
          sub={`Weighted signals, ${r.algorithm_version}. Neutral bars were imputed from the trip median.`}
          actions={
            <span className="tabular font-mono text-[28px] font-semibold leading-none tracking-[-0.03em] text-ice">
              {focus.fit_score ?? "—"}
            </span>
          }
        >
          <SignalBars signals={focus.signals} />
        </Panel>

        <Panel
          title={recommended ? `Why ${recommended.operator_name}` : "No eligible quote yet"}
          sub={
            recommended
              ? `${passed} of ${r.checks.length} checks passed${r.computed_at ? ` · computed ${fmtDateTime(r.computed_at)}` : ""}`
              : "Every quote is blocked by at least one reason in the ranking below."
          }
        >
          {r.checks.length ? (
            <ul className="flex flex-col gap-2.5">
              {r.checks.map((c) => (
                <li
                  key={c.key}
                  className={cn(
                    "flex items-center gap-3 rounded-xl border px-3 py-2.5 text-[13px]",
                    c.passed ? "border-green/20 bg-green/[0.04] text-fg" : "border-line text-fg-muted",
                  )}
                >
                  <span
                    className={cn(
                      "grid h-5 w-5 shrink-0 place-items-center rounded-full",
                      c.passed ? "bg-green/20 text-green" : "bg-white/[0.06] text-fg-dim",
                    )}
                  >
                    {c.passed ? <Check className="h-3 w-3" strokeWidth={3} aria-label="Passed" /> : <X className="h-3 w-3" strokeWidth={3} aria-label="Not passed" />}
                  </span>
                  {c.label}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-fg-dim">Checks appear once a quote is recommended.</p>
          )}
          <dl className="mt-5 grid gap-2 border-t border-line pt-4 text-[11.5px] leading-relaxed text-fg-dim">
            <div>
              <dt className="inline text-fg-muted">Field confidence</dt> — how sure extraction is about one value.
            </div>
            <div>
              <dt className="inline text-fg-muted">Quote confidence</dt> — the weakest material field; verified values count as 100.
            </div>
            <div>
              <dt className="inline text-fg-muted">Fit</dt> — how well the quote matches this trip, from the eight weighted signals.
            </div>
          </dl>
        </Panel>
      </div>

      <Panel title="Ranking" sub="Select a row to see its breakdown. Only eligible quotes can be recommended." bodyClassName="p-0 sm:p-0">
        <TableScroll className="px-5 pt-3">
          <table className="w-full min-w-[760px] border-separate border-spacing-0 text-[13px]">
            <thead>
              <tr>
                <th className={thCls}>#</th>
                <th className={thCls}>Operator</th>
                <th className={cn(thCls, "text-right")}>Fit</th>
                <th className={cn(thCls, "text-right")}>True cost</th>
                <th className={thCls}>Confidence</th>
                <th className={thCls}>Eligibility</th>
              </tr>
            </thead>
            <tbody>
              {r.ranking.map((e) => {
                const isRec = e.quote_id === r.recommended_quote_id;
                const isFocus = e.quote_id === focus.quote_id;
                return (
                  <tr
                    key={e.quote_id}
                    onClick={() => setPicked(e.quote_id)}
                    className={cn("cursor-pointer transition-colors hover:bg-white/[0.02]", isFocus && "bg-white/[0.035]")}
                  >
                    <td className={cn(tdCls, "tabular font-mono text-fg-dim")}>{e.rank}</td>
                    <td className={tdCls}>
                      <div className="flex flex-wrap items-center gap-2">
                        <Link
                          href={`/trips/${tripId}/quotes/${e.quote_id}`}
                          onClick={(ev) => ev.stopPropagation()}
                          className="text-fg hover:text-cyan"
                        >
                          {e.operator_name}
                        </Link>
                        {isRec && <RecommendedTag />}
                      </div>
                    </td>
                    <td className={cn(tdCls, "tabular text-right font-mono text-fg")}>{e.fit_score ?? "—"}</td>
                    <td className={cn(tdCls, "text-right")}>
                      <TrueCostCell known={e.known_total_cents} upper={e.upper_total_cents} fullyPriced={e.is_fully_priced} />
                    </td>
                    <td className={tdCls}>
                      {e.quote_confidence != null ? <ConfidenceBadge value={e.quote_confidence} /> : "—"}
                    </td>
                    <td className={tdCls}>
                      {e.eligible ? (
                        <span className="text-[12px] text-green">Eligible</span>
                      ) : (
                        <ul className="flex flex-col gap-0.5 text-[12px] text-amber">
                          {e.reasons.map((x) => (
                            <li key={x.code}>{x.message}</li>
                          ))}
                          {!e.reasons.length && <li>Ineligible</li>}
                        </ul>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </TableScroll>
      </Panel>
    </div>
  );
}
