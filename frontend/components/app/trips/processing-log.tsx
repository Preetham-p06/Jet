"use client";

import { useEffect, useRef, useState } from "react";
import { endpoints, type ProcessingEvent } from "@/lib/api/endpoints";
import { errorMessage, usePoll } from "@/lib/api/hooks";
import { StatusDot } from "@/components/ui/status-dot";
import { cn } from "@/lib/utils";

const tf = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });

function merge(prev: ProcessingEvent[], next: ProcessingEvent[]): ProcessingEvent[] {
  const seen = new Set(prev.map((e) => e.id));
  const out = [...prev, ...next.filter((e) => !seen.has(e.id))];
  out.sort((a, b) => a.created_at.localeCompare(b.created_at));
  return out.slice(-300);
}

/**
 * Live pipeline log in the style of the landing page's ProcessingLog. Polls
 * `GET /trips/{id}/events?since=` quickly while `live`, slowly otherwise.
 */
export function LiveProcessingLog({
  tripId,
  live,
  className,
  maxHeight = 320,
  refreshKey,
}: {
  tripId: string;
  live: boolean;
  className?: string;
  maxHeight?: number;
  /** Changes whenever the trip's data changed (e.g. an ingest settled); fetches new events at once. */
  refreshKey?: number;
}) {
  const [events, setEvents] = useState<ProcessingEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const lastRef = useRef<string | null>(null);
  const boxRef = useRef<HTMLDivElement>(null);

  async function fetchMore() {
    try {
      const page = await endpoints.events(tripId, lastRef.current);
      setError(null);
      setLoaded(true);
      if (page.items.length) {
        const newest = page.items.reduce((a, e) => (e.created_at > a ? e.created_at : a), lastRef.current ?? "");
        lastRef.current = newest || lastRef.current;
        setEvents((prev) => merge(prev, page.items));
      }
    } catch (e) {
      setLoaded(true);
      setError(errorMessage(e));
    }
  }

  useEffect(() => {
    let alive = true;
    lastRef.current = null;
    endpoints.events(tripId).then(
      (page) => {
        if (!alive) return;
        const m = merge([], page.items);
        lastRef.current = m[m.length - 1]?.created_at ?? null;
        setEvents(m);
        setLoaded(true);
      },
      (e) => {
        if (!alive) return;
        setLoaded(true);
        setError(errorMessage(e));
      },
    );
    return () => {
      alive = false;
    };
  }, [tripId]);

  usePoll(fetchMore, live ? 1200 : 8000, true);

  // Inline-mode extraction finishes before the idle poll fires, so pull the
  // new events as soon as the caller reports a change instead of up to 8 s later.
  const fetchMoreRef = useRef(fetchMore);
  useEffect(() => {
    fetchMoreRef.current = fetchMore;
  });
  const firstKey = useRef(refreshKey);
  useEffect(() => {
    if (refreshKey === firstKey.current) return;
    firstKey.current = refreshKey;
    void fetchMoreRef.current();
  }, [refreshKey]);

  useEffect(() => {
    const el = boxRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [events.length]);

  return (
    <div
      className={cn(
        "flex flex-col rounded-2xl border border-line bg-[linear-gradient(180deg,#0d131c,#0a0e14)] p-4 font-mono text-[11px] leading-5",
        className,
      )}
    >
      <div className="mb-3 flex items-center justify-between">
        <span className="eyebrow text-[10px] text-fg-dim">JetStream intelligence</span>
        <span className="inline-flex items-center gap-1.5 text-[10px] text-fg-dim">
          <StatusDot tone={live ? "cyan" : "green"} pulse={!live} />
          {live ? "LIVE" : "IDLE"}
        </span>
      </div>
      <div
        ref={boxRef}
        data-testid="processing-log"
        className="overflow-y-auto pr-1"
        style={{ maxHeight }}
        aria-live="polite"
        aria-relevant="additions"
      >
        {!loaded ? (
          <p className="shimmer-text">Connecting…</p>
        ) : error && !events.length ? (
          <p className="text-fg-dim">{error}</p>
        ) : !events.length ? (
          <p className="text-fg-dim">No processing events yet. Upload a quote to start.</p>
        ) : (
          <ul className="flex flex-col gap-0.5">
            {events.map((e) => (
              <li key={e.id} className="flex gap-2.5">
                <span className="shrink-0 text-fg-dim">{tf.format(new Date(e.created_at))}</span>
                <span className="hidden w-[104px] shrink-0 uppercase tracking-[0.08em] text-fg-dim/80 sm:inline">{e.step}</span>
                <span
                  className={cn(
                    "min-w-0 break-words text-fg-muted",
                    e.level === "warn" && "text-amber",
                    e.level === "ok" && "text-green",
                    e.level === "error" && "text-red-300",
                  )}
                >
                  {e.message}
                </span>
              </li>
            ))}
            {live && (
              <li className="flex gap-2.5">
                <span className="shrink-0 text-fg-dim">--:--:--</span>
                <span className="inline-block h-3.5 w-1.5 translate-y-[3px] animate-pulse bg-cyan/70 motion-reduce:animate-none" />
              </li>
            )}
          </ul>
        )}
      </div>
    </div>
  );
}
