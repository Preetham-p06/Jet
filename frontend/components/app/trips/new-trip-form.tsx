"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Plus, Trash2 } from "lucide-react";
import { endpoints, type AircraftCategory, type TripCreate } from "@/lib/api/endpoints";
import { useMutation } from "@/lib/api/hooks";
import { GlowButton } from "@/components/ui/glow-button";
import { cn } from "@/lib/utils";
import { AirportInput } from "../airport-input";
import { CATEGORY_LABEL, parseMoneyToCents } from "../fmt";
import { useCan } from "../me-provider";
import { Btn, Field, InlineError, Panel, Segmented, inputCls, textareaCls } from "../ui";

type TripType = "one_way" | "round_trip" | "multi_leg";
type Leg = { key: number; origin: string; destination: string; depart: string };

let legSeq = 1;
const newLeg = (origin = "", destination = ""): Leg => ({ key: legSeq++, origin, destination, depart: "" });

export function NewTripForm() {
  const router = useRouter();
  const canWrite = useCan("trip.write");
  const [tripType, setTripType] = useState<TripType>("one_way");
  // Fixed key for the first leg so server and client render the same ids.
  const [legs, setLegs] = useState<Leg[]>(() => [{ key: 0, origin: "", destination: "", depart: "" }]);
  const [pax, setPax] = useState(4);
  const [wifi, setWifi] = useState(false);
  const [catering, setCatering] = useState(false);
  const [cats, setCats] = useState<AircraftCategory[]>([]);
  const [localError, setLocalError] = useState<string | null>(null);
  const create = useMutation(endpoints.createTrip);

  function setType(t: TripType) {
    setTripType(t);
    setLegs((ls) => {
      if (t === "one_way") return ls.slice(0, 1);
      if (t === "round_trip") {
        const first = ls[0];
        return [first, ls[1] ?? newLeg(first.destination, first.origin)];
      }
      return ls.length >= 2 ? ls : [...ls, newLeg(ls[ls.length - 1].destination)];
    });
  }

  function updateLeg(key: number, patch: Partial<Leg>) {
    setLegs((ls) => ls.map((l) => (l.key === key ? { ...l, ...patch } : l)));
  }

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setLocalError(null);
    const data = new FormData(e.currentTarget);
    for (const [i, l] of legs.entries()) {
      if (!l.origin || !l.destination || !l.depart) {
        setLocalError(`Leg ${i + 1} needs an origin, a destination and a departure time.`);
        return;
      }
      if (l.origin === l.destination) {
        setLocalError(`Leg ${i + 1} departs and arrives at the same airport.`);
        return;
      }
    }
    const budgetRaw = String(data.get("budget") ?? "");
    const budget = budgetRaw ? parseMoneyToCents(budgetRaw) : null;
    if (budgetRaw && budget == null) {
      setLocalError("Budget must be a dollar amount, e.g. 45,000.");
      return;
    }
    const str = (k: string) => {
      const v = String(data.get(k) ?? "").trim();
      return v || null;
    };
    const body: TripCreate = {
      reference: str("reference"),
      trip_type: tripType,
      pax,
      client_name: str("client_name"),
      client_email: str("client_email"),
      notes: str("notes"),
      preferences: {
        wifi_required: wifi,
        catering_required: catering,
        preferred_categories: cats,
        max_budget_cents: budget,
      },
      legs: legs.map((l) => ({
        origin_icao: l.origin,
        destination_icao: l.destination,
        depart_local: l.depart.length === 16 ? `${l.depart}:00` : l.depart,
      })),
    };
    const trip = await create.run(body);
    if (trip) router.push(`/trips/${trip.id}`);
  }

  return (
    <form onSubmit={onSubmit} className="mt-8 grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
      <div className="flex min-w-0 flex-col gap-5">
        <Panel
          title="Itinerary"
          sub="Local departure times at each origin airport."
          actions={
            <Segmented
              label="Trip type"
              value={tripType}
              onChange={setType}
              options={[
                { value: "one_way", label: "One way" },
                { value: "round_trip", label: "Round trip" },
                { value: "multi_leg", label: "Multi-leg" },
              ]}
            />
          }
        >
          <ol className="flex flex-col gap-4">
            {legs.map((l, i) => (
              <li key={l.key} className="rounded-xl border border-line bg-white/[0.015] p-3.5 sm:p-4">
                <div className="mb-3 flex items-center justify-between">
                  <span className="font-mono text-[10.5px] uppercase tracking-[0.16em] text-fg-dim">Leg {i + 1}</span>
                  {tripType === "multi_leg" && legs.length > 2 && (
                    <Btn
                      tone="ghost"
                      size="xs"
                      aria-label={`Remove leg ${i + 1}`}
                      onClick={() => setLegs((ls) => ls.filter((x) => x.key !== l.key))}
                    >
                      <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                    </Btn>
                  )}
                </div>
                <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_1fr_1.1fr]">
                  <Field label="From" htmlFor={`o-${l.key}`}>
                    <AirportInput
                      id={`o-${l.key}`}
                      label={`Leg ${i + 1} origin`}
                      value={l.origin}
                      onChange={(icao) => updateLeg(l.key, { origin: icao })}
                      required
                    />
                  </Field>
                  <Field label="To" htmlFor={`d-${l.key}`}>
                    <AirportInput
                      id={`d-${l.key}`}
                      label={`Leg ${i + 1} destination`}
                      value={l.destination}
                      placeholder="KOPF or Opa-locka"
                      onChange={(icao) => updateLeg(l.key, { destination: icao })}
                      required
                    />
                  </Field>
                  <Field label="Departs (local)" htmlFor={`t-${l.key}`}>
                    <input
                      id={`t-${l.key}`}
                      type="datetime-local"
                      required
                      value={l.depart}
                      onChange={(e) => updateLeg(l.key, { depart: e.target.value })}
                      className={cn(inputCls, "[color-scheme:dark]")}
                    />
                  </Field>
                </div>
              </li>
            ))}
          </ol>
          {tripType === "multi_leg" && (
            <Btn
              className="mt-4"
              onClick={() => setLegs((ls) => [...ls, newLeg(ls[ls.length - 1]?.destination ?? "")])}
            >
              <Plus className="h-3.5 w-3.5" aria-hidden="true" /> Add leg
            </Btn>
          )}
        </Panel>

        <Panel title="Client">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Client name" htmlFor="client_name">
              <input id="client_name" name="client_name" className={inputCls} placeholder="Private client" />
            </Field>
            <Field label="Client email" htmlFor="client_email" hint="Never shared with operators.">
              <input id="client_email" name="client_email" type="email" className={inputCls} />
            </Field>
            <Field label="Reference" htmlFor="reference" hint="Leave blank to auto-number.">
              <input id="reference" name="reference" className={cn(inputCls, "font-mono")} placeholder="JS185" />
            </Field>
            <Field label="Notes" htmlFor="notes" className="sm:col-span-2">
              <textarea id="notes" name="notes" className={textareaCls} placeholder="Pets, luggage, ground transport…" />
            </Field>
          </div>
        </Panel>
      </div>

      <div className="flex min-w-0 flex-col gap-5">
        <Panel title="Passengers & preferences" sub="Feeds the fit score's aircraft and preference signals.">
          <div className="flex flex-col gap-5">
            <Field label="Passengers" htmlFor="pax">
              <div className="flex items-center gap-2">
                <Btn aria-label="Fewer passengers" onClick={() => setPax((p) => Math.max(1, p - 1))}>
                  −
                </Btn>
                <input
                  id="pax"
                  type="number"
                  min={1}
                  max={500}
                  required
                  value={pax}
                  onChange={(e) => setPax(Math.max(1, Number(e.target.value) || 1))}
                  className={cn(inputCls, "tabular w-20 text-center")}
                />
                <Btn aria-label="More passengers" onClick={() => setPax((p) => p + 1)}>
                  +
                </Btn>
              </div>
            </Field>

            <div className="flex flex-col gap-2.5">
              <Toggle label="Wi-Fi required" checked={wifi} onChange={setWifi} />
              <Toggle label="Catering required" checked={catering} onChange={setCatering} />
            </div>

            <fieldset>
              <legend className="text-[12.5px] font-medium text-fg-muted">Preferred categories</legend>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {(Object.keys(CATEGORY_LABEL) as AircraftCategory[]).map((c) => {
                  const on = cats.includes(c);
                  return (
                    <button
                      key={c}
                      type="button"
                      aria-pressed={on}
                      onClick={() => setCats((cs) => (on ? cs.filter((x) => x !== c) : [...cs, c]))}
                      className={cn(
                        "h-7 rounded-full border px-2.5 text-[11.5px] transition-colors",
                        on ? "border-cyan/35 bg-cyan/[0.08] text-ice" : "border-line text-fg-muted hover:text-fg",
                      )}
                    >
                      {CATEGORY_LABEL[c]}
                    </button>
                  );
                })}
              </div>
            </fieldset>

            <Field label="Max budget (USD)" htmlFor="budget" hint="Optional. Quotes above it lose preference points.">
              <input id="budget" name="budget" inputMode="decimal" className={cn(inputCls, "tabular")} placeholder="50,000" />
            </Field>
          </div>
        </Panel>

        <div className="flex flex-col gap-3">
          {localError && (
            <p role="alert" className="text-xs text-amber">
              {localError}
            </p>
          )}
          <InlineError error={create.error} />
          <GlowButton
            type="submit"
            size="lg"
            className="w-full"
            disabled={create.pending || !canWrite}
            icon={<ArrowRight className="h-4 w-4" />}
          >
            {create.pending ? "Creating…" : "Create trip"}
          </GlowButton>
          {!canWrite && <p className="text-xs text-fg-dim">Your role can&apos;t create trips.</p>}
        </div>
      </div>
    </form>
  );
}

function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex cursor-pointer items-center justify-between gap-3 rounded-xl border border-line bg-white/[0.015] px-3 py-2.5 text-[13px] text-fg">
      {label}
      <span className="relative inline-flex">
        <input
          type="checkbox"
          role="switch"
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
          className="peer sr-only"
        />
        <span
          aria-hidden="true"
          className="h-5 w-9 rounded-full border border-line-strong bg-white/[0.05] transition-colors peer-checked:border-cyan/40 peer-checked:bg-cyan/25 peer-focus-visible:outline-2 peer-focus-visible:outline-cyan"
        />
        <span
          aria-hidden="true"
          className="absolute left-0.5 top-0.5 h-4 w-4 rounded-full bg-fg-muted transition-transform peer-checked:translate-x-4 peer-checked:bg-ice"
        />
      </span>
    </label>
  );
}
