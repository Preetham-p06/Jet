import type { ReactNode } from "react";
import { CheckCircle2, Clock, Star, Users, Wifi, WifiOff } from "lucide-react";
import type { PublicProposal } from "@/lib/api/endpoints";
import { categoryLabel, formatCents, formatDuration } from "@/lib/format";
import { cn } from "@/lib/utils";

const longDate = new Intl.DateTimeFormat("en-US", { weekday: "long", month: "long", day: "numeric", year: "numeric" });

function dateText(d: string): string {
  const parsed = new Date(d.length === 10 ? `${d}T12:00:00` : d);
  return Number.isNaN(parsed.getTime()) ? d : longDate.format(parsed);
}

/**
 * The client-facing proposal, mirroring the landing page's ClientView
 * (components/landing/proposal-demo.tsx). Built only from `PublicProposalOut`,
 * so it can never show operators, fees, confidence or markup.
 */
export function ClientProposal({
  proposal,
  renderAction,
  className,
}: {
  proposal: PublicProposal;
  /** Per-option action slot (e.g. the Accept button on /p/[token]). */
  renderAction?: (optionId: string) => ReactNode;
  className?: string;
}) {
  const p = { ...proposal, legs: proposal.legs ?? [], options: proposal.options ?? [] };
  const first = p.legs[0];
  const last = p.legs[p.legs.length - 1];
  const accepted = p.accepted_option_id ?? null;
  const cols = p.options.length >= 3 ? "md:grid-cols-3" : p.options.length === 2 ? "md:grid-cols-2" : "md:max-w-md md:mx-auto";

  return (
    <div className={className}>
      <div className="flex flex-wrap items-center justify-between gap-2 font-mono text-[10.5px] uppercase tracking-[0.12em] text-fg-dim">
        <span>Prepared for · {p.prepared_for ?? "Private client"}</span>
        <span>Prepared by · {p.prepared_by}</span>
      </div>

      <div className="mt-10 text-center">
        <p className="eyebrow">{p.title || "Your private charter options"}</p>
        <h1 className="mt-4 text-[30px] font-semibold tracking-[-0.03em] text-fg sm:text-[38px]">
          {first ? first.origin_city : "—"} <span className="text-fg-dim">→</span> {last ? last.destination_city : "—"}
        </h1>
        <p className="mt-2 text-[15px] text-fg-muted">
          {dateText(p.date)} · {p.pax} passenger{p.pax === 1 ? "" : "s"}
        </p>
        {p.legs.length > 1 && (
          <p className="mt-1 text-[13px] text-fg-dim">
            {p.legs.map((l) => `${l.origin_city} → ${l.destination_city}`).join(" · ")}
          </p>
        )}
        {p.message && <p className="mx-auto mt-6 max-w-xl whitespace-pre-line text-[14px] leading-relaxed text-fg-muted">{p.message}</p>}
      </div>

      <ul className={cn("mt-10 grid gap-4", cols)}>
        {p.options.map((o) => {
          const isAccepted = accepted === o.option_id;
          return (
            <li
              key={o.option_id}
              className={cn(
                "relative flex flex-col rounded-2xl border p-6",
                isAccepted
                  ? "border-green/40 bg-[linear-gradient(180deg,rgba(101,211,155,0.08),rgba(255,255,255,0.02))]"
                  : o.recommended
                    ? "border-amber/40 bg-[linear-gradient(180deg,rgba(246,185,91,0.08),rgba(255,255,255,0.02))] shadow-[0_0_0_1px_rgba(246,185,91,0.12),0_30px_60px_-30px_rgba(246,185,91,0.35)]"
                    : "border-line bg-white/[0.02]",
              )}
            >
              {isAccepted ? (
                <span className="absolute -top-3 left-6 inline-flex items-center gap-1.5 rounded-full border border-green/40 bg-[#0f1c16] px-2.5 py-1 font-mono text-[10px] tracking-[0.14em] text-green">
                  <CheckCircle2 className="h-3 w-3" aria-hidden="true" /> ACCEPTED
                </span>
              ) : (
                o.recommended && (
                  <span className="absolute -top-3 left-6 inline-flex items-center gap-1.5 rounded-full border border-amber/40 bg-[#1c1710] px-2.5 py-1 font-mono text-[10px] tracking-[0.14em] text-amber">
                    <Star className="h-3 w-3 fill-current" aria-hidden="true" /> RECOMMENDED
                  </span>
                )
              )}
              <p className="text-[20px] font-semibold tracking-[-0.02em] text-fg">{o.aircraft}</p>
              <p className="mt-0.5 text-[12.5px] text-fg-dim">{o.category ? categoryLabel(o.category) : "Private jet"}</p>
              <p className="tabular mt-6 text-[28px] font-semibold leading-none tracking-[-0.03em] text-fg" data-testid="client-total">
                {formatCents(o.client_total_cents)}
              </p>
              <p className="mt-1.5 text-[12.5px] text-fg-muted">estimated total, all known charges included</p>
              <ul className="mt-6 space-y-2 border-t border-line pt-5 text-[13px] text-fg-muted">
                <li className="flex items-center gap-2.5">
                  <Users className="h-3.5 w-3.5 text-fg-dim" aria-hidden="true" />
                  {o.seats != null ? `${o.seats} seats · ` : ""}
                  {o.pax} passengers
                </li>
                <li className="flex items-center gap-2.5">
                  {o.wifi ? (
                    <Wifi className="h-3.5 w-3.5 text-fg-dim" aria-hidden="true" />
                  ) : (
                    <WifiOff className="h-3.5 w-3.5 text-fg-dim" aria-hidden="true" />
                  )}
                  {o.wifi == null ? "Wi-Fi to be confirmed" : o.wifi ? "Wi-Fi on board" : "No Wi-Fi"}
                </li>
                <li className="flex items-center gap-2.5">
                  <Clock className="h-3.5 w-3.5 text-fg-dim" aria-hidden="true" /> {formatDuration(o.flight_time_minutes)} flight time
                </li>
              </ul>
              {renderAction && <div className="mt-6">{renderAction(o.option_id)}</div>}
            </li>
          );
        })}
      </ul>
      <p className="mx-auto mt-8 max-w-2xl text-center text-[12px] text-fg-dim">
        {p.disclaimer ||
          "Estimates include every charge stated in or detected from operator quotes. Final pricing is confirmed at booking."}
      </p>
    </div>
  );
}
