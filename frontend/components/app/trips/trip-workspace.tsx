"use client";

import { useCallback, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Activity,
  ArrowLeft,
  ClipboardCheck,
  FileSignature,
  Flag,
  LayoutDashboard,
  RefreshCw,
  Sparkles,
  Table2,
  Users,
  Wifi,
} from "lucide-react";
import { endpoints } from "@/lib/api/endpoints";
import { useApi, useMutation } from "@/lib/api/hooks";
import { ApiError } from "@/lib/api/errors";
import { cn } from "@/lib/utils";
import { useCan } from "../me-provider";
import { categoryLabel, fmtLocal, trueCostText } from "../fmt";
import { TripStatusPill } from "../status";
import { Btn, EmptyState, ErrorState, InlineError, Skeleton } from "../ui";
import { TripContext, type TripTab } from "./trip-context";
import { OverviewTab } from "./overview-tab";
import { QuotesTab } from "./quotes-tab";
import { ReviewTab } from "./review-tab";
import { FlagsTab } from "./flags-tab";
import { RecommendationTab } from "./recommendation-tab";
import { ProposalsTab } from "./proposals-tab";
import { ActivityTab } from "./activity-tab";

const TABS: { id: TripTab; label: string; icon: typeof Activity; requires?: "proposal.manage" }[] = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "quotes", label: "Quotes", icon: Table2 },
  { id: "review", label: "Review", icon: ClipboardCheck },
  { id: "flags", label: "Flags", icon: Flag },
  { id: "recommendation", label: "Recommendation", icon: Sparkles },
  { id: "proposals", label: "Proposals", icon: FileSignature, requires: "proposal.manage" },
  { id: "activity", label: "Activity", icon: Activity },
];

export function TripWorkspace({ tripId, initialTab }: { tripId: string; initialTab: TripTab }) {
  const router = useRouter();
  const canProposals = useCan("proposal.manage");
  const canWrite = useCan("trip.write");
  const [tab, setTab] = useState<TripTab>(initialTab === "proposals" && !canProposals ? "overview" : initialTab);
  const [version, setVersion] = useState(0);
  const trip = useApi(`trip:${tripId}`, () => endpoints.trip(tripId), version);
  const recompute = useMutation(() => endpoints.recompute(tripId));

  const bump = useCallback(() => setVersion((v) => v + 1), []);
  const goTab = useCallback(
    (t: TripTab) => {
      setTab(t);
      router.replace(`/trips/${tripId}?tab=${t}`, { scroll: false });
    },
    [router, tripId],
  );

  const ctx = useMemo(
    () => ({ tripId, trip: trip.data, version, bump, goTab }),
    [tripId, trip.data, version, bump, goTab],
  );

  const tabs = TABS.filter((t) => !t.requires || canProposals);
  const t = trip.data;
  const counts = t?.counts;

  if (trip.error && !t) {
    const missing = trip.error instanceof ApiError && trip.error.status === 404;
    return (
      <div className="mx-auto w-full max-w-6xl">
        <BackLink />
        <div className="mt-8">
          {missing ? (
            <EmptyState title="Trip not found">
              It doesn&apos;t exist in this workspace, or it was deleted.{" "}
              <Link href="/trips" className="text-cyan hover:text-ice">
                Back to trips
              </Link>
            </EmptyState>
          ) : (
            <ErrorState error={trip.error} onRetry={trip.reload} />
          )}
        </div>
      </div>
    );
  }

  return (
    <TripContext.Provider value={ctx}>
      <div className="mx-auto w-full max-w-[1320px]">
        <BackLink />

        {/* Header */}
        <header className="mt-3 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="min-w-0">
            {t ? (
              <>
                <div className="flex flex-wrap items-center gap-2.5">
                  <p className="eyebrow">Trip {t.reference}</p>
                  <TripStatusPill status={t.status} />
                </div>
                <h1 className="mt-2 flex flex-wrap items-center gap-x-3 font-mono text-[24px] font-semibold tracking-[-0.02em] text-fg sm:text-[28px]">
                  {t.legs.length ? (
                    [t.legs[0].origin_icao, ...t.legs.map((l) => l.destination_icao)].map((c, i) => (
                      <span key={`${c}-${i}`} className="inline-flex items-center gap-3">
                        {i > 0 && <span className="text-fg-dim">→</span>}
                        {c}
                      </span>
                    ))
                  ) : (
                    <span>{t.reference}</span>
                  )}
                </h1>
                <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-fg-muted">
                  <span>{fmtLocal(t.legs[0]?.depart_local, t.legs[0]?.depart_tz, true)}</span>
                  <span className="inline-flex items-center gap-1">
                    <Users className="h-3.5 w-3.5 text-fg-dim" aria-hidden="true" /> {t.pax} pax
                  </span>
                  {t.preferences?.wifi_required && (
                    <span className="inline-flex items-center gap-1">
                      <Wifi className="h-3.5 w-3.5 text-fg-dim" aria-hidden="true" /> Wi-Fi required
                    </span>
                  )}
                  {!!t.preferences?.preferred_categories?.length && (
                    <span>{t.preferences.preferred_categories.map(categoryLabel).join(", ")}</span>
                  )}
                  {t.client_name && <span className="text-fg-dim">for {t.client_name}</span>}
                </p>
              </>
            ) : (
              <div className="flex flex-col gap-2.5" role="status" aria-label="Loading trip">
                <Skeleton className="h-3 w-24" />
                <Skeleton className="h-8 w-64" />
                <Skeleton className="h-3 w-80 max-w-full" />
              </div>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {t?.recommendation && (
              <div className="rounded-xl border border-cyan/25 bg-cyan/[0.05] px-3 py-2">
                <p className="font-mono text-[9.5px] uppercase tracking-[0.14em] text-fg-dim">Recommended</p>
                <p className="mt-0.5 text-[13px] text-fg">
                  {t.recommendation.operator_name} ·{" "}
                  <span className="tabular font-mono">
                    {trueCostText(t.recommendation.known_total_cents, t.recommendation.is_fully_priced)}
                  </span>
                </p>
              </div>
            )}
            {canWrite && (
              <Btn
                onClick={async () => {
                  const r = await recompute.run();
                  if (r) bump();
                }}
                pending={recompute.pending}
                title="Re-run normalize, validate and score"
              >
                {!recompute.pending && <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />} Recompute
              </Btn>
            )}
          </div>
        </header>
        <InlineError error={recompute.error} className="mt-2 justify-end" />

        {/* Tabs */}
        <nav aria-label="Trip sections" className="sticky top-14 z-20 -mx-4 mt-6 border-b border-line bg-bg/80 px-4 backdrop-blur-xl sm:-mx-6 sm:px-6 lg:top-0 lg:mx-0 lg:px-0">
          <div role="tablist" className="flex gap-1 overflow-x-auto [scrollbar-width:none]">
            {tabs.map(({ id, label, icon: Icon }) => {
              const selected = id === tab;
              const badge =
                id === "review"
                  ? counts?.pending_review
                  : id === "flags"
                    ? counts?.open_blocking_flags
                    : id === "quotes"
                      ? (counts?.quotes ?? t?.quote_count)
                      : undefined;
              return (
                <button
                  key={id}
                  type="button"
                  role="tab"
                  id={`trip-tab-${id}`}
                  aria-selected={selected}
                  aria-controls={`trip-panel-${id}`}
                  onClick={() => goTab(id)}
                  className={cn(
                    "relative flex h-11 shrink-0 items-center gap-2 px-3 text-[13px] transition-colors",
                    selected ? "text-fg" : "text-fg-muted hover:text-fg",
                  )}
                >
                  <Icon className={cn("h-4 w-4", selected ? "text-cyan" : "text-fg-dim")} strokeWidth={1.75} aria-hidden="true" />
                  {label}
                  {!!badge && (
                    <span
                      className={cn(
                        "tabular rounded-full px-1.5 font-mono text-[10px]",
                        id === "quotes" ? "bg-white/[0.06] text-fg-muted" : "bg-amber/15 text-amber",
                      )}
                    >
                      {badge}
                    </span>
                  )}
                  {selected && (
                    <span
                      aria-hidden="true"
                      className="absolute inset-x-2 -bottom-px h-[2px] rounded-full bg-[linear-gradient(90deg,var(--color-cyan),var(--color-blue))] shadow-[0_0_12px_rgba(89,217,255,0.6)]"
                    />
                  )}
                </button>
              );
            })}
          </div>
        </nav>

        <div role="tabpanel" id={`trip-panel-${tab}`} aria-labelledby={`trip-tab-${tab}`} className="mt-6">
          {tab === "overview" && <OverviewTab />}
          {tab === "quotes" && <QuotesTab />}
          {tab === "review" && <ReviewTab />}
          {tab === "flags" && <FlagsTab />}
          {tab === "recommendation" && <RecommendationTab />}
          {tab === "proposals" && canProposals && <ProposalsTab />}
          {tab === "activity" && <ActivityTab />}
        </div>
      </div>
    </TripContext.Provider>
  );
}

function BackLink() {
  return (
    <Link href="/trips" className="inline-flex items-center gap-1.5 text-xs text-fg-dim hover:text-fg">
      <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" /> Trips
    </Link>
  );
}
