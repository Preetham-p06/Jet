/**
 * Friendly API types. Hand-written until `npm run gen:api` produces
 * `lib/api/schema.d.ts` from the backend's openapi.json; then re-export from there.
 */

export type Role = "admin" | "broker" | "assistant";

export type Capability =
  | "trip.write"
  | "ingest"
  | "field.review"
  | "flag.resolve"
  | "proposal.manage"
  | "analytics.view"
  | "audit.view"
  | "workspace.admin"
  | "users.admin";

export type MeUser = {
  id: string;
  email: string;
  full_name: string;
  role: Role;
};

export type MeWorkspace = {
  id: string;
  name: string;
  slug?: string;
  review_threshold?: number;
  default_markup_pct?: number | string;
  base_currency?: string;
};

/** `GET /api/v1/auth/me` */
export type Me = {
  user: MeUser;
  workspace: MeWorkspace;
  role?: Role;
  capabilities: Capability[];
};
