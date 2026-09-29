#!/usr/bin/env node
/**
 * JetStream AI demo walkthrough (spec §13(e)).
 *
 *   BASE_URL=http://localhost:3001 DEMO_PASSWORD=… OUT_DIR=/path/to/shots \
 *     PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers node e2e/demo-flow.mjs
 *
 * Logs in as demo@jetstream.example, walks the broker dashboard, sends a
 * proposal, opens the public link in a fresh context and asserts it leaks no
 * operator names, fee labels or confidence percentages. Screenshots go to
 * OUT_DIR. Exits non-zero if any check fails (after taking every screenshot).
 */
import { mkdir } from "node:fs/promises";
import path from "node:path";

process.env.PLAYWRIGHT_BROWSERS_PATH ??= "/opt/pw-browsers";
const { chromium } = await import("playwright");

const BASE_URL = (process.env.BASE_URL ?? "http://localhost:3001").replace(/\/$/, "");
const PASSWORD = process.env.DEMO_PASSWORD;
const OUT_DIR = process.env.OUT_DIR ?? path.resolve("e2e-shots");
const DEMO_EMAIL = process.env.DEMO_EMAIL ?? "demo@jetstream.example";
const ASSISTANT_EMAIL = process.env.ASSISTANT_EMAIL ?? "assistant@jetstream.example";
const TRIP_REF = process.env.TRIP_REF ?? "JS184";
const MARKUP = 5;
const VIEWPORT = { width: 1440, height: 900 };

if (!PASSWORD) {
  console.error("DEMO_PASSWORD is required");
  process.exit(2);
}
await mkdir(OUT_DIR, { recursive: true });

const failures = [];
let shotNo = 0;
function check(name, ok, detail = "") {
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? `  (${detail})` : ""}`);
  if (!ok) failures.push(`${name}${detail ? `: ${detail}` : ""}`);
}
async function shot(page, name) {
  shotNo += 1;
  const file = path.join(OUT_DIR, `${String(shotNo).padStart(2, "0")}-${name}.png`);
  // Scrolled pages capture the sticky sidebar mid-page; shoot from the top.
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: file, fullPage: true });
  console.log(`      screenshot ${file}`);
}
async function step(name, fn) {
  console.log(`\n== ${name}`);
  try {
    await fn();
  } catch (e) {
    check(name, false, e instanceof Error ? e.message.split("\n")[0] : String(e));
  }
}
async function settle(page) {
  await page.waitForLoadState("networkidle", { timeout: 15_000 }).catch(() => {});
}
async function login(page, email) {
  await page.goto(`${BASE_URL}/login`);
  await page.getByLabel("Work email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL(/\/trips/, { timeout: 20_000 });
  await settle(page);
}
const api = async (page, p) => {
  const res = await page.request.get(`${BASE_URL}/api/v1${p}`, { headers: { "X-JetStream-Client": "web" } });
  if (!res.ok()) throw new Error(`GET ${p} → ${res.status()}`);
  return res.json();
};
const text = async (page) => (await page.locator("body").innerText()).replace(/\s+/g, " ");

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: VIEWPORT });
const page = await ctx.newPage();
let tripId = null;
let shareUrl = null;
let expectedTotals = [];
let operatorNames = [];

// 1. Landing, then Log in
await step("1 landing → log in", async () => {
  await page.goto(`${BASE_URL}/`);
  await settle(page);
  await page.screenshot({ path: path.join(OUT_DIR, "00-landing-hero.png") });
  // Sections animate in on scroll; walk the page so the full-page shot isn't blank.
  const height = await page.evaluate(() => document.body.scrollHeight);
  for (let y = 0; y < height; y += 600) {
    await page.evaluate((top) => window.scrollTo(0, top), y);
    await page.waitForTimeout(120);
  }
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(400);
  await shot(page, "landing");
  await page.getByRole("link", { name: /^log in$/i }).first().click();
  await page.waitForURL(/\/login/);
});

// 2. /login as demo
await step("2 login as demo", async () => {
  await shot(page, "login");
  await login(page, DEMO_EMAIL);
  check("redirected to /trips", page.url().includes("/trips"));
});

// 3. Trips list
await step("3 trips list", async () => {
  await page.getByText(TRIP_REF).first().waitFor({ timeout: 15_000 });
  await shot(page, "trips");
  await page.getByRole("link", { name: TRIP_REF }).first().click();
  await page.waitForURL(/\/trips\/[^/?]+/);
  tripId = page.url().split("/trips/")[1].split(/[?/#]/)[0];
  check("opened trip", !!tripId, tripId ?? "");
});

// 4. Overview with RFQ response times
await step("4 overview", async () => {
  await page.getByText("Operator requests").waitFor();
  await page.getByText(/Median response/).waitFor({ timeout: 15_000 });
  await settle(page);
  const t = await text(page);
  check("RFQ response times shown", /\d+\.\d h/.test(t));
  await shot(page, "overview");
});

// 5. Comparison
await step("5 comparison", async () => {
  await page.getByRole("tab", { name: /Quotes/ }).click();
  await page.getByText("Quote comparison").waitFor();
  const summitRow = page.locator("tr", { hasText: "Summit" }).first();
  await summitRow.waitFor({ timeout: 20_000 });
  await settle(page);
  const t = await text(page);
  check("Atlas true cost $44,820", t.includes("$44,820"));
  check("Summit shows $41,980+", (await summitRow.innerText()).includes("$41,980+"));
  const atlasRow = page.locator("tr", { hasText: "Atlas" }).first();
  check("Atlas row is RECOMMENDED", (await atlasRow.innerText()).includes("RECOMMENDED"));
  await shot(page, "comparison");
});

// 6. Review queue
await step("6 review queue", async () => {
  await page.getByRole("tab", { name: /Review/ }).click();
  await page.getByText("Review queue").first().waitFor();
  await page.getByText(/\d+%/).first().waitFor({ timeout: 20_000 }).catch(() => {});
  await settle(page);
  const t = await text(page);
  check("Summit fuel at 61% in queue", /Summit/.test(t) && /61%/.test(t));
  await shot(page, "review");
});

// 7. Flags
await step("7 flags", async () => {
  await page.getByRole("tab", { name: /Flags/ }).click();
  await page.getByText(/Ambiguous charge/i).first().waitFor({ timeout: 20_000 }).catch(() => {});
  await settle(page);
  const t = await text(page);
  check("ambiguous charge flag listed", /Ambiguous charge/i.test(t));
  await shot(page, "flags");
});

// 8. Recommendation
await step("8 recommendation", async () => {
  await page.getByRole("tab", { name: /Recommendation/ }).click();
  await page.getByText("Ranking").waitFor();
  await page.getByText(/checks passed/).first().waitFor({ timeout: 20_000 }).catch(() => {});
  await settle(page);
  const t = await text(page);
  check("Atlas fit 96", /Fit breakdown · Atlas/.test(t) && /\b96\b/.test(t));
  check("5 of 5 checks", /5 of 5 checks passed/.test(t));
  await shot(page, "recommendation");
});

// 8b. Assistant: actions hidden or disabled (runs before the SMS revision clears the queue)
await step("8b assistant role", async () => {
  const actx = await browser.newContext({ viewport: VIEWPORT });
  const ap = await actx.newPage();
  await login(ap, ASSISTANT_EMAIL);
  check("assistant nav hides Analytics", (await ap.getByRole("link", { name: "Analytics" }).count()) === 0);
  await ap.goto(`${BASE_URL}/trips/${tripId}?tab=review`);
  await ap.getByText("Review queue").first().waitFor();
  await ap.getByRole("button", { name: /Verify/ }).first().waitFor({ timeout: 20_000 }).catch(() => {});
  await settle(ap);
  const verify = ap.getByRole("button", { name: /Verify/ });
  const n = await verify.count();
  let allDisabled = n > 0;
  for (let i = 0; i < n; i++) allDisabled &&= await verify.nth(i).isDisabled();
  check("assistant cannot verify", allDisabled, `${n} verify buttons`);
  check("proposals tab hidden", (await ap.getByRole("tab", { name: /Proposals/ }).count()) === 0);
  await shot(ap, "assistant-review");
  await actx.close();
});

// 9. Paste a new SMS revision and watch the log
await step("9 paste SMS revision", async () => {
  await page.getByRole("tab", { name: /Quotes/ }).click();
  const logItems = page.locator("[data-testid=processing-log] li");
  await logItems.first().waitFor({ timeout: 20_000 });
  const before = await logItems.count();
  await page.getByRole("radio", { name: "Paste" }).click();
  await page.locator("#ingest-text").fill(
    "Hi it's Dan at Summit re JS184 KTEB-KOPF 18 Oct. Revised: fuel confirmed included, 38,900 all in, crew overnight 700 extra. Thx",
  );
  const opt = page.locator("#ingest-op option", { hasText: "Summit" }).first();
  const value = await opt.getAttribute("value").catch(() => null);
  if (value) await page.locator("#ingest-op").selectOption(value);
  await page.getByRole("button", { name: /Extract quote/ }).click();
  await page.getByText(/Extracted|Failed|Needs manual/).first().waitFor({ timeout: 90_000 });
  await page
    .locator("[data-testid=processing-log]", { hasText: "Received SMS message" })
    .waitFor({ timeout: 5_000 })
    .catch(() => {});
  await page.waitForTimeout(500);
  await shot(page, "processing-log");
  const after = await logItems.count();
  const logText = await page.locator("[data-testid=processing-log]").innerText();
  check("live log shows the new SMS events", after > before && /Received SMS message/.test(logText), `${before} → ${after} lines`);
});

// 10. Proposal builder with 5% markup, then send
await step("10 proposal builder + send", async () => {
  await page.getByRole("tab", { name: /Proposals/ }).click();
  await page.getByRole("button", { name: /New proposal/ }).click();
  await page.locator("#markup").waitFor({ timeout: 20_000 });
  await page.locator("#markup").fill(String(MARKUP));
  await page.getByRole("button", { name: /^Save$/ }).click();
  await settle(page);
  await page.getByRole("radio", { name: "Broker view" }).click();
  await shot(page, "proposal-broker");
  await page.getByRole("radio", { name: "Client view" }).click();
  await shot(page, "proposal-client-preview");
  await page.getByRole("button", { name: /Send to client/ }).click();
  const url = page.getByTestId("share-url");
  await url.waitFor({ timeout: 20_000 });
  shareUrl = (await url.innerText()).trim();
  check("share link issued", /\/p\/[A-Za-z0-9_-]{16,}/.test(shareUrl), shareUrl);
  await shot(page, "proposal-sent");

  const proposals = await api(page, `/trips/${tripId}/proposals`);
  const sent = proposals.items.find((p) => p.status === "sent");
  const detail = await api(page, `/proposals/${sent.id}`);
  operatorNames = detail.options.map((o) => o.operator_name);
  expectedTotals = detail.options
    .map((o) => Math.round((o.cost_basis_cents / 100) * (1 + MARKUP / 100)))
    .sort((a, b) => a - b);
});

// 11. Public page in a fresh context
await step("11 public proposal", async () => {
  if (!shareUrl) throw new Error("no share URL");
  const pub = await browser.newContext({ viewport: VIEWPORT });
  const pp = await pub.newPage();
  const u = new URL(shareUrl);
  await pp.goto(`${BASE_URL}${u.pathname}`);
  await settle(pp);
  await shot(pp, "public-proposal");
  const html = await pp.content();
  const t = await text(pp);
  const vocab = await api(page, "/meta/vocabulary");
  const feeLabels = vocab.fee_categories.map((c) => c.label);
  const leakedOps = [...new Set([...operatorNames, "Atlas"])].filter((n) => html.includes(n));
  check("no operator names in DOM", leakedOps.length === 0, leakedOps.join(", "));
  const leakedFees = feeLabels.filter((l) => t.includes(l));
  check("no fee labels on page", leakedFees.length === 0, leakedFees.join(", "));
  check("no % confidence on page", !/\d+\s?%/.test(t));
  const shown = (await pp.getByTestId("client-total").allInnerTexts())
    .map((s) => Number(s.replace(/[^0-9]/g, "")))
    .sort((a, b) => a - b);
  check(
    "client totals equal known × 1.05",
    shown.length > 0 && JSON.stringify(shown) === JSON.stringify(expectedTotals),
    `shown ${shown.join(",")} expected ${expectedTotals.join(",")}`,
  );
  const robots = await pp.locator('meta[name="robots"]').getAttribute("content");
  check("public page is noindex", /noindex/.test(robots ?? ""));
  await pub.close();
});

// 12. Analytics
await step("12 analytics", async () => {
  await page.goto(`${BASE_URL}/analytics`);
  await page.getByText("Quote volume").waitFor({ timeout: 20_000 });
  await settle(page);
  await shot(page, "analytics");
});

// 14. New workspace cannot see JS184
await step("14 tenant isolation", async () => {
  const nctx = await browser.newContext({ viewport: VIEWPORT });
  const np = await nctx.newPage();
  await np.goto(`${BASE_URL}/signup`);
  const stamp = Date.now();
  await np.locator('input[name="workspace_name"]').fill(`Isolation Check ${stamp}`);
  await np.locator('input[name="full_name"]').fill("Isolation Tester");
  await np.locator('input[name="email"]').fill(`iso-${stamp}@example.com`);
  await np.locator('input[name="password"]').fill(`Iso-${stamp}-password!`);
  await np.getByRole("button", { name: /create|sign up|get started/i }).click();
  await np.waitForURL(/\/trips/, { timeout: 20_000 });
  await np.goto(`${BASE_URL}/trips/${tripId}`);
  await np.getByText(/Trip not found|Not found/).first().waitFor({ timeout: 20_000 });
  check("other workspace's trip is not found", true);
  await shot(np, "isolation-not-found");
  await nctx.close();
});

await browser.close();
console.log(`\n${failures.length ? `${failures.length} check(s) failed` : "All checks passed"}. Screenshots in ${OUT_DIR}`);
if (failures.length) {
  for (const f of failures) console.log(`  - ${f}`);
  process.exit(1);
}
