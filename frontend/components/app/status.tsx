import { AlertOctagon, AlertTriangle, Info } from "lucide-react";
import type { FlagSeverity, ProposalStatus, TripOperatorStatus, TripStatus } from "@/lib/api/endpoints";
import { cn } from "@/lib/utils";
import { humanize } from "./fmt";
import { Pill, type Tone } from "./ui";

const TRIP_TONE: Record<TripStatus, Tone> = {
  draft: "neutral",
  sourcing: "blue",
  quoted: "cyan",
  proposed: "amber",
  booked: "green",
  cancelled: "neutral",
  lost: "red",
};

export function TripStatusPill({ status }: { status: TripStatus }) {
  return (
    <Pill tone={TRIP_TONE[status] ?? "neutral"} dot>
      {humanize(status)}
    </Pill>
  );
}

const PROPOSAL_TONE: Record<ProposalStatus, Tone> = {
  draft: "neutral",
  sent: "cyan",
  accepted: "green",
  booked: "green",
  declined: "red",
  cancelled: "neutral",
  superseded: "neutral",
};

export function ProposalStatusPill({ status }: { status: ProposalStatus }) {
  return (
    <Pill tone={PROPOSAL_TONE[status] ?? "neutral"} dot>
      {humanize(status)}
    </Pill>
  );
}

const RFQ_TONE: Record<TripOperatorStatus, Tone> = { requested: "blue", quoted: "green", declined: "neutral" };

export function RfqStatusPill({ status }: { status: TripOperatorStatus }) {
  return (
    <Pill tone={RFQ_TONE[status] ?? "neutral"} dot>
      {humanize(status)}
    </Pill>
  );
}

export function SeverityIcon({ severity, className }: { severity: FlagSeverity; className?: string }) {
  const cls = cn("h-4 w-4 shrink-0", className);
  if (severity === "critical")
    return <AlertOctagon className={cn(cls, "text-red-300")} aria-label="Critical" strokeWidth={1.9} />;
  if (severity === "warning")
    return <AlertTriangle className={cn(cls, "text-amber")} aria-label="Warning" strokeWidth={1.9} />;
  return <Info className={cn(cls, "text-fg-dim")} aria-label="Info" strokeWidth={1.9} />;
}

export function SeverityPill({ severity, blocking }: { severity: FlagSeverity; blocking?: boolean }) {
  const tone: Tone = severity === "critical" ? "red" : severity === "warning" ? "amber" : "neutral";
  return (
    <Pill tone={tone}>
      {severity.toUpperCase()}
      {blocking ? " · BLOCKING" : ""}
    </Pill>
  );
}
