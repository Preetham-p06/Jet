/**
 * All content on the landing page is fictional demo data.
 * Operators, aircraft availability, prices and flight IDs are invented
 * for visual demonstration and do not describe real companies or trips.
 */

export const NAV_LINKS = [
  { label: "Product", href: "#product" },
  { label: "How it works", href: "#how-it-works" },
  { label: "Intelligence", href: "#intelligence" },
  { label: "Pricing", href: "#pricing" },
] as const;

export const CONTACT_HREF = "mailto:hello@jetstream.example?subject=JetStream%20early%20access";

/* ---------------------------------------------------------------- */
/* Charter request + quotes (hero product shell)                     */
/* ---------------------------------------------------------------- */

export const REQUEST = {
  id: "JS184",
  from: "New York",
  fromCode: "KTEB",
  to: "Miami",
  toCode: "KOPF",
  date: "Oct 18",
  dateLong: "October 18",
  pax: 7,
  depart: "Fri · 9:00 AM",
} as const;

export type FeeLine = {
  label: string;
  /** null = included */
  amount: number | null;
  source: string;
  page?: number;
  confidence: number;
  flagged?: boolean;
};

export type Quote = {
  id: string;
  operator: string;
  aircraft: string;
  category: string;
  headline: number;
  fees: FeeLine[];
  trueCost: number;
  fit: number;
  finalFit: number;
  seats: number;
  wifi: boolean;
  flightTime: string;
  sourceFile: string;
  recommended?: boolean;
  /** Missing / ambiguous charge detected */
  warning?: string;
};

export const QUOTES: Quote[] = [
  {
    id: "q-atlas",
    operator: "Atlas Air Charter",
    aircraft: "Citation Latitude",
    category: "Midsize",
    headline: 41_800,
    fees: [
      { label: "Positioning", amount: 1_200, source: "atlas_quote_01.pdf", page: 1, confidence: 96 },
      { label: "Ramp / handling", amount: 420, source: "atlas_quote_01.pdf", page: 2, confidence: 94 },
      { label: "Fuel surcharge", amount: 1_400, source: "atlas_quote_01.pdf", page: 2, confidence: 92 },
      { label: "Catering", amount: null, source: "email · Oct 2", confidence: 98 },
    ],
    trueCost: 44_820,
    fit: 94,
    finalFit: 97,
    seats: 8,
    wifi: true,
    flightTime: "2h 58m",
    sourceFile: "atlas_quote_01.pdf",
    recommended: true,
  },
  {
    id: "q-skybridge",
    operator: "SkyBridge Aviation",
    aircraft: "Challenger 350",
    category: "Super-midsize",
    headline: 45_900,
    fees: [
      { label: "Positioning", amount: 850, source: "quote-final-v7.pdf", page: 1, confidence: 95 },
      { label: "Ramp / handling", amount: 450, source: "quote-final-v7.pdf", page: 1, confidence: 93 },
      { label: "Catering", amount: null, source: "quote-final-v7.pdf", page: 2, confidence: 97 },
    ],
    trueCost: 47_200,
    fit: 91,
    finalFit: 91,
    seats: 9,
    wifi: true,
    flightTime: "2h 48m",
    sourceFile: "quote-final-v7.pdf",
  },
  {
    id: "q-northstar",
    operator: "Northstar Jets",
    aircraft: "Gulfstream G280",
    category: "Super-midsize",
    headline: 50_200,
    fees: [
      { label: "Positioning", amount: 1_400, source: "operator_quote_18.pdf", page: 1, confidence: 97 },
      { label: "Ramp / handling", amount: 800, source: "operator_quote_18.pdf", page: 1, confidence: 90 },
      { label: "Catering", amount: null, source: "operator_quote_18.pdf", page: 1, confidence: 96 },
    ],
    trueCost: 52_400,
    fit: 86,
    finalFit: 86,
    seats: 9,
    wifi: true,
    flightTime: "2h 45m",
    sourceFile: "operator_quote_18.pdf",
  },
  {
    id: "q-summit",
    operator: "Summit Executive Aviation",
    aircraft: "Legacy 650",
    category: "Heavy",
    headline: 38_900,
    fees: [
      { label: "Positioning", amount: 1_900, source: "revised-quote.pdf", page: 1, confidence: 93 },
      { label: "Ramp / handling", amount: 480, source: "revised-quote.pdf", page: 2, confidence: 88 },
      { label: "Crew overnight", amount: 700, source: "text message · Oct 3", confidence: 84 },
      { label: "Fuel surcharge", amount: null, source: "text message · Oct 3", confidence: 61, flagged: true },
    ],
    trueCost: 41_980,
    fit: 83,
    finalFit: 83,
    seats: 13,
    wifi: false,
    flightTime: "3h 05m",
    sourceFile: "revised-quote.pdf",
    warning: "Fuel surcharge not stated",
  },
];

export const RECOMMENDED = QUOTES[0];

/**
 * Hero shell processing log (fictional telemetry).
 * `at` is the demo step at which the line appears.
 */
export type LogTone = "default" | "warn" | "ok";
export const LOG_LINES: { t: string; text: string; at: number; tone?: LogTone }[] = [
  { t: "09:42:11", text: "Ingest atlas_quote_01.pdf", at: 1 },
  { t: "09:42:11", text: "Ingest quote-final-v7.pdf", at: 2 },
  { t: "09:42:11", text: "Ingest operator_quote_18.pdf", at: 3 },
  { t: "09:42:12", text: "Ingest revised-quote.pdf + SMS", at: 4 },
  { t: "09:42:12", text: "Extracting · 4 documents", at: 5 },
  { t: "09:42:12", text: "31 fields detected", at: 6 },
  { t: "09:42:13", text: "Positioning fees · 4 of 4", at: 6 },
  { t: "09:42:13", text: "Fuel surcharge missing · flag", at: 7, tone: "warn" },
  { t: "09:42:13", text: "Totals normalized · 4 quotes", at: 8 },
  { t: "09:42:14", text: "Confidence updated · 97%", at: 8 },
  { t: "09:42:14", text: "Recommendation ready", at: 9, tone: "ok" },
];

/* ---------------------------------------------------------------- */
/* Trust strip                                                       */
/* ---------------------------------------------------------------- */

export const TRUST_POINTS = [
  "Fast to deploy",
  "Human verified",
  "Broker-first workflow",
  "Pilot partners coming soon",
] as const;

/* ---------------------------------------------------------------- */
/* Problem section                                                   */
/* ---------------------------------------------------------------- */

export type FragmentKind = "pdf" | "email" | "chat" | "sms";

export const FRAGMENTS: { kind: FragmentKind; text: string; meta: string }[] = [
  { kind: "pdf", text: "operator_01.pdf", meta: "2 pages · scanned" },
  { kind: "chat", text: "“$39,500 incl. standard charges…”", meta: "WhatsApp · 09:12" },
  { kind: "pdf", text: "quote-final-v7.pdf", meta: "revised twice" },
  { kind: "sms", text: "“Fuel may be extra”", meta: "SMS · 11:48" },
  { kind: "email", text: "RE: RE: Availability KTEB–KOPF", meta: "thread · 14 replies" },
  { kind: "pdf", text: "operator_quote_18.pdf", meta: "hourly rate only" },
];

export const ENGINE_STAGES = ["Extract", "Normalize", "Validate", "Compare"] as const;

/* ---------------------------------------------------------------- */
/* Before / after                                                    */
/* ---------------------------------------------------------------- */

export const BEFORE_ITEMS = [
  "12 operator replies across email, PDF and text",
  "Comparison spreadsheet rebuilt for every trip",
  "Copy-paste of hourly rates, taxes and fees",
  "Ramp, crew and fuel charges buried in footnotes",
  "Follow-up emails to confirm what was included",
  "Pricing that cannot be compared line for line",
];

export const AFTER_ITEMS = [
  "One workspace for every incoming quote",
  "Normalized quotes with the same line items",
  "True cost, not headline price",
  "Exceptions and missing charges flagged",
  "Every figure verified with a confidence score",
  "Client-ready proposal in one action",
];

/* ---------------------------------------------------------------- */
/* True-cost waterfall (illustrative demo quote)                     */
/* ---------------------------------------------------------------- */

export const WATERFALL_META = {
  flightId: "JX421",
  route: "Teterboro → Palm Beach",
  file: "operator_quote_03.pdf",
} as const;

export const WATERFALL: FeeLine[] = [
  { label: "Operator quote", amount: 42_500, source: "operator_quote_03.pdf", page: 1, confidence: 99 },
  { label: "Positioning", amount: 1_200, source: "operator_quote_03.pdf", page: 1, confidence: 96 },
  { label: "Ramp / handling", amount: 420, source: "operator_quote_03.pdf", page: 2, confidence: 94 },
  { label: "Crew overnight", amount: 700, source: "email · Sep 28", confidence: 91 },
  { label: "Catering", amount: null, source: "operator_quote_03.pdf", page: 2, confidence: 97 },
  { label: "International fees", amount: 350, source: "operator_quote_03.pdf", page: 3, confidence: 89 },
];

export const WATERFALL_TOTAL = 45_170;

/* ---------------------------------------------------------------- */
/* Intelligence section                                              */
/* ---------------------------------------------------------------- */

export const SIGNALS = [
  "Aircraft",
  "Pricing",
  "Availability",
  "Routing",
  "Fees",
  "Crew",
  "Timing",
  "Client preferences",
] as const;

export const RECOMMENDATION_CHECKS = [
  "Best schedule fit",
  "Lowest fully-priced total cost",
  "Wi-Fi on board",
  "8-seat configuration",
  "No overnight crew requirement",
] as const;

/* ---------------------------------------------------------------- */
/* Workflow                                                          */
/* ---------------------------------------------------------------- */

export const WORKFLOW_STAGES = [
  { n: "01", title: "Request", detail: "NYC → Miami · 7 passengers · Friday 9:00 AM" },
  { n: "02", title: "Broadcast", detail: "8 operators contacted" },
  { n: "03", title: "Extract", detail: "31 fields found" },
  { n: "04", title: "Normalize", detail: "5 fees detected · 4 quotes compared" },
  { n: "05", title: "Proposal", detail: "Client-ready options" },
] as const;

/* ---------------------------------------------------------------- */
/* Proposal                                                          */
/* ---------------------------------------------------------------- */

export const PROPOSAL_OPTIONS = QUOTES.filter((q) => !q.warning).map((q) => ({
  id: q.id,
  aircraft: q.aircraft,
  category: q.category,
  total: q.trueCost,
  seats: q.seats,
  wifi: q.wifi,
  flightTime: q.flightTime,
  recommended: Boolean(q.recommended),
}));

/* ---------------------------------------------------------------- */
/* Roadmap                                                           */
/* ---------------------------------------------------------------- */

export const ROADMAP = [
  { title: "Quote ingestion", status: "Now", detail: "PDFs, emails and messages become structured, comparable quotes." },
  { title: "Operator intelligence", status: "Planned", detail: "Response times, pricing patterns and reliability by operator." },
  { title: "Client preference memory", status: "Planned", detail: "Aircraft, catering and timing preferences remembered per client." },
  { title: "Automated negotiation", status: "Planned", detail: "Counter-offers and clarifications drafted for broker approval." },
  { title: "Trip / contract workflows", status: "Planned", detail: "From accepted proposal to contract and trip sheet." },
] as const;

/* ---------------------------------------------------------------- */
/* Analytics demo (sample workspace data — fictional)                */
/* ---------------------------------------------------------------- */

export const ANALYTICS = {
  quoteVolume: [12, 18, 15, 22, 27, 24, 31, 29, 35, 33, 41, 38],
  responseTimes: [
    { operator: "Atlas Air", hours: 1.4 },
    { operator: "SkyBridge", hours: 2.1 },
    { operator: "Northstar", hours: 3.6 },
    { operator: "Summit Exec.", hours: 5.2 },
  ],
  feeTypes: [
    { label: "Positioning", pct: 84 },
    { label: "Ramp / handling", pct: 71 },
    { label: "Fuel surcharge", pct: 46 },
    { label: "Crew overnight", pct: 29 },
    { label: "International", pct: 12 },
  ],
  aircraftMix: [
    { label: "Midsize", pct: 38 },
    { label: "Super-mid", pct: 34 },
    { label: "Heavy", pct: 18 },
    { label: "Light", pct: 10 },
  ],
  funnel: [
    { label: "Requests", value: 120 },
    { label: "Quotes received", value: 96 },
    { label: "Proposals sent", value: 64 },
    { label: "Trips booked", value: 22 },
  ],
} as const;

/* ---------------------------------------------------------------- */
/* Integrations (all planned — none implemented)                     */
/* ---------------------------------------------------------------- */

export const INTEGRATIONS = [
  { label: "Gmail", kind: "mail" },
  { label: "Outlook", kind: "mail" },
  { label: "PDF inbox", kind: "pdf" },
  { label: "CRM", kind: "crm" },
  { label: "Aviation marketplaces", kind: "market" },
  { label: "Operator portals", kind: "portal" },
] as const;

/* ---------------------------------------------------------------- */
/* Security                                                          */
/* ---------------------------------------------------------------- */

export const SECURITY_POINTS = [
  { title: "Role-based access", detail: "Brokers, assistants and admins see only what their role needs." },
  { title: "Secure document handling", detail: "Operator files stay inside the workspace they were sent to." },
  { title: "Audit-friendly workflow", detail: "Every extracted figure links back to its source document." },
  { title: "Human verification", detail: "Low-confidence fields require a broker before they reach a client." },
  { title: "No flight-control systems", detail: "JetStream is broker productivity software. It never touches aircraft operations." },
] as const;

/* ---------------------------------------------------------------- */
/* FAQ                                                               */
/* ---------------------------------------------------------------- */

export const FAQ = [
  {
    q: "What types of quotes can JetStream process?",
    a: "PDF quotes, plain-text emails, forwarded messages and other unstructured operator responses. Each one is read, extracted into the same structured fields and normalized so it can be compared line for line.",
  },
  {
    q: "Does JetStream replace our existing charter tools?",
    a: "No. JetStream is an intelligence and workflow layer for the quotes you already receive. It sits alongside your existing sourcing, CRM and trip tools.",
  },
  {
    q: "Can I verify AI-extracted information?",
    a: "Yes. Every field carries a confidence score and a link to its source. Anything below your threshold is flagged for a one-click review before it reaches a proposal.",
  },
  {
    q: "Does JetStream control aircraft or flight operations?",
    a: "No. JetStream is broker productivity software. It never connects to aircraft, flight-control or dispatch systems.",
  },
  {
    q: "Can JetStream create client-ready proposals?",
    a: "Yes. Once quotes are normalized and verified, JetStream assembles a clean side-by-side proposal you can send to a client.",
  },
  {
    q: "How does JetStream handle uncertain data?",
    a: "Ambiguous figures are scored, flagged and held for human verification. Nothing uncertain is presented to a client as fact.",
  },
] as const;

/* ---------------------------------------------------------------- */
/* Footer                                                            */
/* ---------------------------------------------------------------- */

export const FOOTER_LINKS = [
  { label: "Product", href: "#product" },
  { label: "How it works", href: "#how-it-works" },
  { label: "Security", href: "#security" },
  { label: "Pricing", href: "#pricing" },
  { label: "Contact", href: CONTACT_HREF },
] as const;
