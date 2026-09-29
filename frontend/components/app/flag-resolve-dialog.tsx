"use client";

import { useState } from "react";
import { endpoints, type Flag, type FlagResolution, type FlagType } from "@/lib/api/endpoints";
import { useMutation } from "@/lib/api/hooks";
import { cn } from "@/lib/utils";
import { formatCents, humanize, parseMoneyToCents } from "./fmt";
import { SeverityPill } from "./status";
import { Btn, Dialog, Field, InlineError, inputCls, textareaCls } from "./ui";

/** Spec §4 flag table: the resolutions each flag type allows (used when the API omits them). */
export const RESOLUTIONS_BY_TYPE: Partial<Record<FlagType, FlagResolution[]>> = {
  ambiguous_charge: ["confirmed_amount", "accepted_estimate", "confirmed_included", "not_applicable", "dismissed"],
  expected_fee_missing: ["confirmed_amount", "confirmed_included", "not_applicable", "dismissed"],
  learned_fee_missing: ["confirmed_amount", "confirmed_included", "not_applicable", "dismissed"],
  conditional_charge: ["acknowledged"],
  total_mismatch: ["acknowledged"],
  conflicting_values: ["use_new_value", "keep_current"],
  conflict_with_locked: ["use_new_value", "keep_current"],
  capacity_insufficient: ["dismissed"],
  hourly_estimate: ["confirmed_amount", "acknowledged"],
  quote_expired: ["acknowledged"],
  all_in_itemized_conflict: ["acknowledged"],
  fx_converted: ["acknowledged"],
  snippet_unverified: ["acknowledged"],
  fee_outlier: ["acknowledged"],
  schedule_mismatch: ["acknowledged"],
  value_revised: ["acknowledged"],
};

/** Flags that clear themselves once an edit or reprocess fixes the data. */
export const AUTO_CLEAR_HINT: Partial<Record<FlagType, string>> = {
  missing_required_field: "Clears automatically when an edit supplies the missing value. Edit the field from the quote page.",
  unknown_currency: "Edit the quote's currency on the quote page; this flag then clears.",
  extraction_failed: "Paste the quote text manually or reprocess the document from the Quotes tab.",
  ocr_unavailable: "Paste the quote text manually or reprocess the document from the Quotes tab.",
};

export const RESOLUTION_LABEL: Record<FlagResolution, { label: string; help: string }> = {
  confirmed_amount: { label: "Confirm an amount", help: "Record the operator-confirmed amount. Creates an edited, locked fee." },
  accepted_estimate: { label: "Accept the estimate", help: "Use the estimated amount as a known charge." },
  confirmed_included: { label: "Confirmed included", help: "The operator confirmed it is included in the price." },
  not_applicable: { label: "Not applicable", help: "This charge does not apply to this trip." },
  dismissed: { label: "Dismiss", help: "Close the flag without changing any value. A note is required." },
  acknowledged: { label: "Acknowledge", help: "Noted. No value changes." },
  use_new_value: { label: "Use the new value", help: "Replace the current value with the newer source." },
  keep_current: { label: "Keep the current value", help: "Ignore the conflicting value." },
  auto_cleared: { label: "Auto-cleared", help: "" },
};

export function allowedResolutions(flag: Flag): FlagResolution[] {
  const fromApi = (flag.allowed_resolutions ?? []).filter((r) => r !== "auto_cleared");
  if (fromApi.length) return fromApi;
  return RESOLUTIONS_BY_TYPE[flag.type] ?? [];
}

export function FlagResolveDialog({
  flag,
  operatorName,
  onClose,
  onResolved,
}: {
  flag: Flag | null;
  operatorName?: string;
  onClose: () => void;
  onResolved: (f: Flag) => void;
}) {
  return flag ? (
    <ResolveInner key={flag.id} flag={flag} operatorName={operatorName} onClose={onClose} onResolved={onResolved} />
  ) : null;
}

function ResolveInner({
  flag,
  operatorName,
  onClose,
  onResolved,
}: {
  flag: Flag;
  operatorName?: string;
  onClose: () => void;
  onResolved: (f: Flag) => void;
}) {
  const options = allowedResolutions(flag);
  const estimate =
    typeof flag.details?.estimate_cents === "number" ? (flag.details.estimate_cents as number) : null;
  const [choice, setChoice] = useState<FlagResolution | null>(options[0] ?? null);
  const [amount, setAmount] = useState(estimate != null ? String(estimate / 100) : "");
  const [note, setNote] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const resolve = useMutation(endpoints.resolveFlag);

  async function submit() {
    setErr(null);
    if (!choice) return;
    let amount_cents: number | null = null;
    if (choice === "confirmed_amount") {
      amount_cents = parseMoneyToCents(amount);
      if (amount_cents == null) return setErr("Enter the confirmed amount.");
    }
    if (choice === "dismissed" && !note.trim()) return setErr("A note is required to dismiss a flag.");
    const res = await resolve.run(flag.id, { resolution: choice, amount_cents, note: note.trim() || null });
    if (res) {
      onResolved(res);
      onClose();
    }
  }

  const hint = AUTO_CLEAR_HINT[flag.type];

  return (
    <Dialog
      open
      onClose={onClose}
      title={`Resolve: ${humanize(flag.type)}`}
      description={
        <span className="flex flex-wrap items-center gap-2">
          <SeverityPill severity={flag.severity} blocking={flag.blocking} />
          {operatorName && <span>{operatorName}</span>}
          {flag.fee_category && <span className="text-fg-dim">· {humanize(flag.fee_category)}</span>}
        </span>
      }
      footer={
        options.length ? (
          <>
            <Btn tone="ghost" onClick={onClose}>
              Cancel
            </Btn>
            <Btn tone="primary" onClick={submit} pending={resolve.pending} disabled={!choice}>
              Resolve flag
            </Btn>
          </>
        ) : (
          <Btn onClick={onClose}>Close</Btn>
        )
      }
    >
      <p className="text-[13px] leading-relaxed text-fg">{flag.message}</p>
      {estimate != null && (
        <p className="mt-1.5 text-xs text-fg-muted">
          Engine estimate: <span className="tabular font-mono text-amber">{formatCents(estimate)}</span>
        </p>
      )}

      {options.length === 0 ? (
        <p className="mt-4 rounded-lg border border-line bg-white/[0.02] px-3 py-2.5 text-xs text-fg-muted">
          {hint ?? "This flag can't be resolved directly."}
        </p>
      ) : (
        <fieldset className="mt-4 flex flex-col gap-2">
          <legend className="sr-only">Resolution</legend>
          {options.map((r) => (
            <label
              key={r}
              className={cn(
                "flex cursor-pointer gap-3 rounded-xl border px-3 py-2.5 transition-colors",
                choice === r ? "border-cyan/35 bg-cyan/[0.05]" : "border-line hover:border-line-strong",
              )}
            >
              <input
                type="radio"
                name="resolution"
                value={r}
                checked={choice === r}
                onChange={() => setChoice(r)}
                className="mt-1 accent-[#59d9ff]"
              />
              <span>
                <span className="block text-[13px] text-fg">{RESOLUTION_LABEL[r]?.label ?? humanize(r)}</span>
                <span className="block text-xs text-fg-dim">{RESOLUTION_LABEL[r]?.help}</span>
              </span>
            </label>
          ))}
        </fieldset>
      )}

      {choice === "confirmed_amount" && (
        <Field label="Confirmed amount (USD)" htmlFor="flag-amount" className="mt-4">
          <div className="relative">
            <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sm text-fg-dim">$</span>
            <input
              id="flag-amount"
              inputMode="decimal"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              className={cn(inputCls, "tabular pl-7 font-mono")}
            />
          </div>
        </Field>
      )}
      {options.length > 0 && (
        <Field label={choice === "dismissed" ? "Note (required)" : "Note"} htmlFor="flag-note" className="mt-4">
          <textarea
            id="flag-note"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            className={cn(textareaCls, "min-h-[72px]")}
            placeholder="Who confirmed it, and how"
          />
        </Field>
      )}
      {err && <p className="mt-3 text-xs text-amber">{err}</p>}
      <InlineError error={resolve.error} className="mt-3" />
    </Dialog>
  );
}
