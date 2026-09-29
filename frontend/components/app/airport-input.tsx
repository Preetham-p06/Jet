"use client";

import { useEffect, useId, useRef, useState } from "react";
import { Loader2, MapPin } from "lucide-react";
import { endpoints, type AirportOut } from "@/lib/api/endpoints";
import { cn } from "@/lib/utils";
import { inputCls } from "./ui";

type Props = {
  id?: string;
  value: string;
  onChange: (icao: string, airport?: AirportOut) => void;
  placeholder?: string;
  label: string;
  required?: boolean;
};

/** ICAO combobox backed by `GET /meta/airports?q=`. Free text is kept as typed (uppercased). */
export function AirportInput({ id, value, onChange, placeholder = "KTEB or Teterboro", label, required }: Props) {
  const listId = useId();
  const [text, setText] = useState(value);
  const [items, setItems] = useState<AirportOut[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [loading, setLoading] = useState(false);
  const [picked, setPicked] = useState<AirportOut | null>(null);
  const [failed, setFailed] = useState(false);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => () => window.clearTimeout(timer.current), []);

  function search(q: string) {
    window.clearTimeout(timer.current);
    if (q.trim().length < 2) {
      setItems([]);
      return;
    }
    timer.current = window.setTimeout(async () => {
      setLoading(true);
      try {
        const res = await endpoints.airports(q.trim());
        setItems(res.items);
        setFailed(false);
        setActive(0);
      } catch {
        setItems([]);
        setFailed(true);
      } finally {
        setLoading(false);
      }
    }, 180);
  }

  function choose(a: AirportOut) {
    setText(a.icao);
    setPicked(a);
    setOpen(false);
    onChange(a.icao, a);
  }

  return (
    <div className="relative">
      <input
        id={id}
        role="combobox"
        aria-label={label}
        aria-expanded={open && items.length > 0}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={open && items[active] ? `${listId}-${active}` : undefined}
        autoComplete="off"
        required={required}
        value={text}
        placeholder={placeholder}
        onChange={(e) => {
          const v = e.target.value;
          setText(v);
          setPicked(null);
          setOpen(true);
          search(v);
          const code = v.trim().toUpperCase();
          onChange(/^[A-Z0-9]{3,4}$/.test(code) ? code : "");
        }}
        onFocus={() => items.length && setOpen(true)}
        onBlur={() => window.setTimeout(() => setOpen(false), 120)}
        onKeyDown={(e) => {
          if (!open || !items.length) return;
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setActive((a) => Math.min(items.length - 1, a + 1));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setActive((a) => Math.max(0, a - 1));
          } else if (e.key === "Enter") {
            e.preventDefault();
            choose(items[active]);
          } else if (e.key === "Escape") {
            setOpen(false);
          }
        }}
        className={cn(inputCls, "pr-8 font-mono uppercase placeholder:normal-case placeholder:font-sans")}
      />
      <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-fg-dim">
        {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> : <MapPin className="h-3.5 w-3.5" aria-hidden="true" />}
      </span>
      {picked && (
        <p className="mt-1 truncate text-[11.5px] text-fg-dim">
          {picked.name} · {picked.city}, {picked.country}
        </p>
      )}
      {failed && !picked && <p className="mt-1 text-[11.5px] text-fg-dim">Airport lookup unavailable; type the ICAO code.</p>}
      {open && items.length > 0 && (
        <ul
          id={listId}
          role="listbox"
          className="glass-strong absolute inset-x-0 top-[calc(100%+6px)] z-30 max-h-64 overflow-y-auto rounded-xl p-1 shadow-card"
        >
          {items.map((a, i) => (
            <li
              key={a.icao}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === active}
              onMouseDown={(e) => {
                e.preventDefault();
                choose(a);
              }}
              onMouseEnter={() => setActive(i)}
              className={cn(
                "flex cursor-pointer items-baseline gap-2.5 rounded-lg px-2.5 py-2 text-[13px]",
                i === active ? "bg-white/[0.07]" : "",
              )}
            >
              <span className="font-mono text-cyan">{a.icao}</span>
              <span className="min-w-0 flex-1 truncate text-fg">{a.name}</span>
              <span className="shrink-0 text-[11.5px] text-fg-dim">{a.city}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
