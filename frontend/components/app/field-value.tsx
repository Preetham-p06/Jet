"use client";

import { useState } from "react";
import type { AmountStatus, FeeValue, Field, MoneyValue } from "@/lib/api/endpoints";
import { cn } from "@/lib/utils";
import { categoryLabel, formatCents, formatDuration, fmtDateTime, humanize, parseMoneyToCents } from "./fmt";
import { inputCls, selectCls } from "./ui";

type Value = Field["current_value"];

function isMoney(v: unknown): v is MoneyValue {
  return !!v && typeof v === "object" && "amount_minor" in v && "currency" in v;
}
function isFee(v: unknown): v is FeeValue {
  return !!v && typeof v === "object" && "category" in v && "status" in v;
}

export function money(v: MoneyValue): string {
  if (v.currency === "USD") return formatCents(v.amount_minor);
  return `${(v.amount_minor / 100).toLocaleString("en-US", { maximumFractionDigits: 2 })} ${v.currency}`;
}

/** Human text for any field value. */
export function displayValue(field: Pick<Field, "value_type" | "key">, v: Value): string {
  if (v === null || v === undefined) return "—";
  if (isFee(v)) {
    const amt = v.amount ? money(v.amount) : v.percent != null ? `${v.percent}%` : null;
    switch (v.status) {
      case "included":
        return "Included";
      case "waived":
        return "Waived";
      case "not_applicable":
        return "Not applicable";
      case "not_stated":
        return "Not stated";
      case "estimated":
        return `est. ${amt ?? "—"}${v.hedged ? " (hedged)" : ""}`;
      default:
        return `${amt ?? "—"}${v.explicitly_extra ? " extra" : ""}`;
    }
  }
  if (isMoney(v)) return money(v);
  if (typeof v === "boolean") return v ? "Yes" : "No";
  if (field.value_type === "duration" && typeof v === "number") return formatDuration(v);
  if (field.value_type === "datetime" && typeof v === "string") return fmtDateTime(v, v);
  if (field.key === "aircraft_category" && typeof v === "string") return categoryLabel(v);
  if (typeof v === "string") return field.key.endsWith("status") || field.key === "availability" ? humanize(v) : v;
  return String(v);
}

/** The substring of `snippet` to highlight for this value. */
export function highlightNeedle(field: Pick<Field, "value_type" | "key">, v: Value): string[] {
  const out: string[] = [];
  const addAmount = (minor: number) => {
    const whole = Math.round(minor / 100);
    out.push(whole.toLocaleString("en-US"), String(whole));
    if (whole >= 1000 && whole % 100 === 0) out.push(`${(whole / 1000).toLocaleString("en-US")}k`);
  };
  if (isFee(v)) {
    if (v.amount) addAmount(v.amount.amount_minor);
    if (v.status === "included") out.push("included", "Included", "all in");
    if (v.status === "estimated") out.push("est.", "may be");
    out.push(v.label);
  } else if (isMoney(v)) addAmount(v.amount_minor);
  else if (typeof v === "number") out.push(String(v));
  else if (typeof v === "string") out.push(v);
  else if (typeof v === "boolean") out.push(v ? "Yes" : "No");
  return out.filter((s) => s && s.length >= 2);
}

export function Snippet({ text, needles, className }: { text: string; needles: string[]; className?: string }) {
  let idx = -1;
  let len = 0;
  const lower = text.toLowerCase();
  for (const n of needles) {
    const i = lower.indexOf(n.toLowerCase());
    if (i >= 0) {
      idx = i;
      len = n.length;
      break;
    }
  }
  return (
    <blockquote
      className={cn(
        "rounded-lg border-l-2 border-amber/50 bg-white/[0.025] px-3 py-2 font-mono text-[12px] leading-relaxed text-fg-muted",
        className,
      )}
    >
      {idx < 0 ? (
        <mark className="bg-transparent text-fg">{text}</mark>
      ) : (
        <>
          {text.slice(0, idx)}
          <mark className="rounded bg-amber/20 px-0.5 text-ice shadow-[0_0_0_1px_rgba(246,185,91,0.35)]">
            {text.slice(idx, idx + len)}
          </mark>
          {text.slice(idx + len)}
        </>
      )}
    </blockquote>
  );
}

const FEE_STATUSES: AmountStatus[] = ["stated", "included", "estimated", "not_stated", "waived", "not_applicable"];

/**
 * Typed inline editor. Calls `onSubmit` with the JSON value the API expects
 * for this field's `value_type` (money → MoneyValue, fee → FeeValue).
 */
export function FieldEditor({
  field,
  onSubmit,
  onCancel,
  pending,
}: {
  field: Field;
  onSubmit: (value: unknown, note: string | null) => void;
  onCancel: () => void;
  pending?: boolean;
}) {
  const v = field.current_value;
  const fee = isFee(v) ? v : null;
  const moneyV = isMoney(v) ? v : fee?.amount ?? null;
  const initialText =
    moneyV != null
      ? String(moneyV.amount_minor / 100)
      : typeof v === "string" || typeof v === "number"
        ? String(v)
        : "";
  const [text, setText] = useState(initialText);
  const [bool, setBool] = useState(typeof v === "boolean" ? v : false);
  const [status, setStatus] = useState<AmountStatus>(fee?.status ?? "stated");
  const [note, setNote] = useState("");
  const [err, setErr] = useState<string | null>(null);

  const currency = moneyV?.currency ?? "USD";
  const needsAmount = field.value_type === "money" || (fee && (status === "stated" || status === "estimated"));

  function submit() {
    setErr(null);
    let value: unknown;
    if (field.value_type === "fee" && fee) {
      let amount: MoneyValue | null = null;
      if (status === "stated" || status === "estimated") {
        const c = parseMoneyToCents(text);
        if (c == null) return setErr("Enter an amount.");
        amount = { amount_minor: c, currency };
      }
      value = { ...fee, status, amount, hedged: false };
    } else if (field.value_type === "money") {
      const c = parseMoneyToCents(text);
      if (c == null) return setErr("Enter an amount.");
      value = { amount_minor: c, currency };
    } else if (field.value_type === "bool") {
      value = bool;
    } else if (field.value_type === "int" || field.value_type === "duration") {
      const n = Number(text);
      if (!Number.isInteger(n)) return setErr("Enter a whole number.");
      value = n;
    } else if (field.value_type === "number") {
      const n = Number(text);
      if (!Number.isFinite(n)) return setErr("Enter a number.");
      value = n;
    } else {
      if (!text.trim()) return setErr("Enter a value.");
      value = text.trim();
    }
    onSubmit(value, note.trim() || null);
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          e.stopPropagation();
          onCancel();
        }
      }}
      className="flex flex-col gap-2.5 rounded-xl border border-cyan/25 bg-cyan/[0.03] p-3"
    >
      <div className="flex flex-wrap gap-2">
        {fee && (
          <select
            aria-label="Amount status"
            value={status}
            onChange={(e) => setStatus(e.target.value as AmountStatus)}
            className={cn(selectCls, "w-40")}
          >
            {FEE_STATUSES.map((s) => (
              <option key={s} value={s}>
                {humanize(s)}
              </option>
            ))}
          </select>
        )}
        {field.value_type === "bool" ? (
          <select
            aria-label="Value"
            value={bool ? "yes" : "no"}
            onChange={(e) => setBool(e.target.value === "yes")}
            className={cn(selectCls, "w-28")}
          >
            <option value="yes">Yes</option>
            <option value="no">No</option>
          </select>
        ) : (fee && !needsAmount) ? null : (
          <div className="relative min-w-[140px] flex-1">
            {needsAmount && <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sm text-fg-dim">{currency === "USD" ? "$" : currency}</span>}
            <input
              autoFocus
              aria-label={`New value for ${field.label ?? field.key}`}
              value={text}
              inputMode={needsAmount || field.value_type === "int" || field.value_type === "number" ? "decimal" : undefined}
              onChange={(e) => setText(e.target.value)}
              className={cn(inputCls, "tabular font-mono", needsAmount && (currency === "USD" ? "pl-7" : "pl-12"))}
              placeholder={field.value_type === "duration" ? "minutes" : undefined}
            />
          </div>
        )}
      </div>
      <input
        aria-label="Note"
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder="Note (optional): e.g. confirmed by phone with Dan"
        className={cn(inputCls, "h-9 text-[12.5px]")}
      />
      {err && <p className="text-xs text-amber">{err}</p>}
      <div className="flex justify-end gap-2">
        <button type="button" onClick={onCancel} className="h-8 rounded-full px-3 text-[12.5px] text-fg-muted hover:text-fg">
          Cancel
        </button>
        <button
          type="submit"
          disabled={pending}
          className="h-8 rounded-full bg-[linear-gradient(135deg,#f2fdff_0%,#9fe9ff_38%,#5b8cff_100%)] px-3.5 text-[12.5px] font-medium text-bg-deep disabled:opacity-50"
        >
          {pending ? "Saving…" : "Save edit"}
        </button>
      </div>
    </form>
  );
}
