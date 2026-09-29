/**
 * Typed browser-side endpoint functions, one per backend route (spec §8).
 * Types come from the generated `schema.d.ts`; paths have no trailing slash.
 */
import type { components } from "./schema";
import { api } from "./client";

type S = components["schemas"];

export type AirportOut = S["AirportOut"];
export type AnalyticsOverview = S["AnalyticsOverviewOut"];
export type AuditEvent = S["AuditEventOut"];
export type Availability = S["Availability"];
export type AircraftCategory = S["AircraftCategory"];
export type AmountStatus = S["AmountStatus"];
export type CheckOut = S["CheckOut"];
export type ComparisonCell = S["ComparisonCellOut"];
export type Comparison = S["ComparisonOut"];
export type ComparisonRow = S["ComparisonRowOut"];
export type DocumentChannel = S["DocumentChannel"];
export type ExtractionStatus = S["ExtractionStatus"];
export type FeeCategory = S["FeeCategory"];
export type FeeLine = S["FeeLineOut"];
export type Field = S["FieldOut"];
export type Flag = S["FlagOut"];
export type FlagResolution = S["FlagResolution"];
export type FlagSeverity = S["FlagSeverity"];
export type FlagStatus = S["FlagStatus"];
export type FlagType = S["FlagType"];
export type IngestOut = S["IngestOut"];
export type Invite = S["InviteOut"];
export type InviteCreated = S["InviteCreatedOut"];
export type LegIn = S["LegIn"];
export type MeOut = S["MeOut"];
export type MoneyValue = S["MoneyValue"];
export type FeeValue = S["FeeValue"];
export type Operator = S["OperatorOut"];
export type OperatorDetail = S["OperatorDetailOut"];
export type OperatorCreate = S["OperatorCreate"];
export type ProcessingEvent = S["ProcessingEventOut"];
export type Proposal = S["ProposalOut"];
export type ProposalOption = S["ProposalOptionOut"];
export type ProposalStatus = S["ProposalStatus"];
export type ProposalSummary = S["ProposalSummaryOut"];
export type PublicProposal = S["PublicProposalOut"];
export type QuoteDetail = S["QuoteDetailOut"];
export type QuoteSummary = S["QuoteSummaryOut"];
export type Reason = S["ReasonOut"];
export type Recommendation = S["RecommendationOut"];
export type RankingEntry = S["RankingEntryOut"];
export type RequestChannel = S["RequestChannel"];
export type ReviewItem = S["ReviewQueueItemOut"];
export type Role = S["Role"];
export type Signal = S["SignalOut"];
export type SourceDocument = S["SourceDocumentOut"];
export type SourceDocumentDetail = S["SourceDocumentDetailOut"];
export type SourceRef = S["SourceRefOut"];
export type TripCreate = S["TripCreate"];
export type TripOperator = S["TripOperatorOut"];
export type TripOperatorStatus = S["TripOperatorStatus"];
export type Trip = S["TripOut"];
export type TripPreferences = S["TripPreferences"];
export type TripStatus = S["TripStatus"];
export type TripSummary = S["TripSummaryOut"];
export type User = S["UserOut"];
export type Vocabulary = S["VocabularyOut"];
export type Workspace = S["WorkspaceOut"];
export type WorkspacePatch = S["WorkspacePatch"];

export type Page<T> = { items: T[]; total: number };

type Query = Record<string, string | number | boolean | null | undefined>;

/** `{a: 1, b: undefined}` → `?a=1`. */
export function qs(q: Query = {}): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(q)) {
    if (v === undefined || v === null || v === "") continue;
    p.set(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : "";
}

const enc = encodeURIComponent;

/** Link to a source document's original bytes, opened at a PDF page. */
export function sourceFileUrl(documentId: string, page?: number | null): string {
  return `/api/v1/source-documents/${enc(documentId)}/file${page ? `#page=${page}` : ""}`;
}

/* ---------------- auth / workspace / users ---------------- */
export const endpoints = {
  me: () => api<MeOut>("/auth/me"),
  changePassword: (current_password: string, new_password: string) =>
    api<MeOut>("/auth/change-password", { json: { current_password, new_password } }),

  workspace: () => api<Workspace>("/workspace"),
  patchWorkspace: (body: WorkspacePatch) => api<Workspace>("/workspace", { method: "PATCH", json: body }),

  users: () => api<Page<User>>(`/users${qs({ limit: 200 })}`),
  patchUser: (id: string, body: S["UserPatch"]) => api<User>(`/users/${enc(id)}`, { method: "PATCH", json: body }),
  invites: () => api<Page<Invite>>(`/invites${qs({ limit: 200 })}`),
  createInvite: (body: S["InviteCreate"]) => api<InviteCreated>("/invites", { json: body }),
  revokeInvite: (id: string) => api<void>(`/invites/${enc(id)}`, { method: "DELETE" }),

  /* ---------------- meta ---------------- */
  vocabulary: () => api<Vocabulary>("/meta/vocabulary"),
  airports: (q: string, limit = 8) => api<Page<AirportOut>>(`/meta/airports${qs({ q, limit })}`),

  /* ---------------- operators ---------------- */
  operators: (q: { q?: string; include_archived?: boolean; limit?: number; offset?: number } = {}) =>
    api<Page<Operator>>(`/operators${qs({ limit: 200, ...q })}`),
  operator: (id: string) => api<OperatorDetail>(`/operators/${enc(id)}`),
  createOperator: (body: OperatorCreate) => api<Operator>("/operators", { json: body }),
  patchOperator: (id: string, body: S["OperatorPatch"]) =>
    api<Operator>(`/operators/${enc(id)}`, { method: "PATCH", json: body }),
  archiveOperator: (id: string) => api<void>(`/operators/${enc(id)}`, { method: "DELETE" }),

  /* ---------------- trips ---------------- */
  trips: (q: { status?: string; q?: string; limit?: number; offset?: number } = {}) =>
    api<Page<TripSummary>>(`/trips${qs({ limit: 50, ...q })}`),
  createTrip: (body: TripCreate) => api<Trip>("/trips", { json: body }),
  trip: (id: string) => api<Trip>(`/trips/${enc(id)}`),
  patchTrip: (id: string, body: S["TripPatch"]) => api<Trip>(`/trips/${enc(id)}`, { method: "PATCH", json: body }),
  deleteTrip: (id: string) => api<void>(`/trips/${enc(id)}`, { method: "DELETE" }),
  recompute: (id: string) => api<Recommendation>(`/trips/${enc(id)}/recompute`, { method: "POST" }),
  events: (id: string, since?: string | null) =>
    api<Page<ProcessingEvent>>(`/trips/${enc(id)}/events${qs({ since, limit: 200 })}`),

  tripOperators: (id: string) => api<Page<TripOperator>>(`/trips/${enc(id)}/operators${qs({ limit: 200 })}`),
  addTripOperators: (id: string, body: S["TripOperatorsAdd"]) =>
    api<Page<TripOperator>>(`/trips/${enc(id)}/operators`, { json: body }),
  patchTripOperator: (id: string, toId: string, body: S["TripOperatorPatch"]) =>
    api<TripOperator>(`/trips/${enc(id)}/operators/${enc(toId)}`, { method: "PATCH", json: body }),
  removeTripOperator: (id: string, toId: string) =>
    api<void>(`/trips/${enc(id)}/operators/${enc(toId)}`, { method: "DELETE" }),

  /* ---------------- documents & quotes ---------------- */
  ingest: (tripId: string, form: FormData) => api<IngestOut>(`/trips/${enc(tripId)}/quotes/ingest`, { form }),
  sourceDocuments: (tripId: string) =>
    api<Page<SourceDocument>>(`/trips/${enc(tripId)}/source-documents${qs({ limit: 200 })}`),
  sourceDocument: (id: string) => api<SourceDocumentDetail>(`/source-documents/${enc(id)}`),
  reprocess: (id: string) => api<SourceDocument>(`/source-documents/${enc(id)}/reprocess`, { method: "POST" }),
  moveDocument: (id: string, body: S["DocumentMoveIn"]) =>
    api<SourceDocument>(`/source-documents/${enc(id)}/move`, { json: body }),

  quotes: (tripId: string) => api<Page<QuoteSummary>>(`/trips/${enc(tripId)}/quotes${qs({ limit: 200 })}`),
  comparison: (tripId: string) => api<Comparison>(`/trips/${enc(tripId)}/comparison`),
  quote: (id: string) => api<QuoteDetail>(`/quotes/${enc(id)}`),
  patchQuote: (id: string, body: S["QuotePatch"]) =>
    api<QuoteSummary>(`/quotes/${enc(id)}`, { method: "PATCH", json: body }),
  addField: (quoteId: string, body: S["ManualFieldIn"]) =>
    api<Field>(`/quotes/${enc(quoteId)}/fields`, { json: body }),

  /* ---------------- review ---------------- */
  reviewQueue: (tripId: string) => api<Page<ReviewItem>>(`/trips/${enc(tripId)}/review-queue`),
  fieldHistory: (id: string) => api<Page<Field>>(`/fields/${enc(id)}/history`),
  verifyField: (id: string, version: number) => api<Field>(`/fields/${enc(id)}/verify`, { json: { version } }),
  acceptField: (id: string, version: number, note?: string | null) =>
    api<Field>(`/fields/${enc(id)}/accept`, { json: { version, note: note ?? null } }),
  editField: (id: string, version: number, value: unknown, note?: string | null) =>
    api<Field>(`/fields/${enc(id)}`, { method: "PATCH", json: { version, value, note: note ?? null } }),
  resetField: (id: string, version: number) => api<Field>(`/fields/${enc(id)}/reset`, { json: { version } }),

  /* ---------------- flags ---------------- */
  flags: (tripId: string, q: { status?: FlagStatus; quote_id?: string } = {}) =>
    api<Page<Flag>>(`/trips/${enc(tripId)}/flags${qs({ limit: 200, ...q })}`),
  resolveFlag: (id: string, body: S["FlagResolveIn"]) => api<Flag>(`/flags/${enc(id)}/resolve`, { json: body }),
  reopenFlag: (id: string) => api<Flag>(`/flags/${enc(id)}/reopen`, { method: "POST" }),

  /* ---------------- recommendation ---------------- */
  recommendation: (tripId: string) => api<Recommendation>(`/trips/${enc(tripId)}/recommendation`),

  /* ---------------- proposals ---------------- */
  proposals: (q: { trip_id?: string; status?: ProposalStatus } = {}) =>
    api<Page<ProposalSummary>>(`/proposals${qs({ limit: 100, ...q })}`),
  tripProposals: (tripId: string) =>
    api<Page<ProposalSummary>>(`/trips/${enc(tripId)}/proposals${qs({ limit: 100 })}`),
  createProposal: (tripId: string, body: S["ProposalCreate"]) =>
    api<Proposal>(`/trips/${enc(tripId)}/proposals`, { json: body }),
  proposal: (id: string) => api<Proposal>(`/proposals/${enc(id)}`),
  patchProposal: (id: string, body: S["ProposalPatch"]) =>
    api<Proposal>(`/proposals/${enc(id)}`, { method: "PATCH", json: body }),
  clientPreview: (id: string) => api<PublicProposal>(`/proposals/${enc(id)}/client-preview`),
  proposalAction: (
    id: string,
    action: "send" | "rotate-link" | "revoke-link" | "decline" | "cancel" | "revise",
  ) => api<Proposal>(`/proposals/${enc(id)}/${action}`, { method: "POST" }),
  proposalChoice: (id: string, action: "mark-accepted" | "mark-booked", option_id?: string | null) =>
    api<Proposal>(`/proposals/${enc(id)}/${action}`, { json: { option_id: option_id ?? null } }),

  /* ---------------- public ---------------- */
  acceptPublic: (token: string, option_id: string, name: string) =>
    api<PublicProposal>(`/public/proposals/${enc(token)}/accept`, {
      json: { option_id, name },
      redirectOn401: false,
    }),

  /* ---------------- analytics / audit ---------------- */
  analytics: (q: { date_from?: string; date_to?: string } = {}) =>
    api<AnalyticsOverview>(`/analytics/overview${qs(q)}`),
  auditEvents: (q: {
    trip_id?: string;
    entity_type?: string;
    action?: string;
    actor_user_id?: string;
    date_from?: string;
    date_to?: string;
    limit?: number;
    offset?: number;
  }) => api<Page<AuditEvent>>(`/audit-events${qs({ limit: 50, ...q })}`),
};
