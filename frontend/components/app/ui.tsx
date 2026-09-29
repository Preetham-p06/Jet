"use client";

import { useEffect, useId, useRef, type ReactNode } from "react";
import { AlertTriangle, Construction, Inbox, Loader2, RefreshCw, X } from "lucide-react";
import { ApiError, fieldLabel } from "@/lib/api/errors";
import { errorMessage } from "@/lib/api/hooks";
import { cn } from "@/lib/utils";

/* ------------------------------------------------------------------ */
/* Form control classes (match components/auth/form-field.tsx)         */
/* ------------------------------------------------------------------ */
export const inputCls = cn(
  "h-10 w-full rounded-xl border border-line bg-white/[0.03] px-3 text-sm text-fg",
  "placeholder:text-fg-dim transition-[border-color,background-color,box-shadow] duration-200",
  "hover:border-line-strong focus:border-cyan/45 focus:bg-white/[0.05] focus:outline-none focus:ring-2 focus:ring-cyan/15",
  "disabled:cursor-not-allowed disabled:opacity-60",
);
export const selectCls = cn(inputCls, "appearance-none bg-[#0c1119] pr-8");
export const textareaCls = cn(inputCls, "h-auto min-h-[96px] py-2.5 leading-relaxed");
export const labelCls = "text-[12.5px] font-medium text-fg-muted";

export function Field({
  label,
  hint,
  error,
  htmlFor,
  children,
  className,
}: {
  label: string;
  hint?: ReactNode;
  /** A field-level message, e.g. from `fieldErrorOf(mutation.error, "email")`. */
  error?: string | null;
  htmlFor?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex min-w-0 flex-col gap-1.5", className)}>
      <label htmlFor={htmlFor} className={labelCls}>
        {label}
      </label>
      {children}
      {error ? <FieldMessage>{error}</FieldMessage> : hint && <p className="text-xs text-fg-dim">{hint}</p>}
    </div>
  );
}

/** A field-level error message under an input. */
export function FieldMessage({ children, className }: { children: ReactNode; className?: string }) {
  if (!children) return null;
  return <p className={cn("text-xs text-amber", className)}>{children}</p>;
}

/* ------------------------------------------------------------------ */
/* Buttons                                                             */
/* ------------------------------------------------------------------ */
type BtnProps = {
  children: ReactNode;
  onClick?: () => void;
  type?: "button" | "submit";
  disabled?: boolean;
  tone?: "default" | "primary" | "danger" | "ghost" | "amber";
  size?: "xs" | "sm" | "md";
  className?: string;
  title?: string;
  pending?: boolean;
  "aria-label"?: string;
  "aria-keyshortcuts"?: string;
};

/** Compact action button for dense product UI (GlowButton is for hero actions). */
export function Btn({
  children,
  onClick,
  type = "button",
  disabled,
  tone = "default",
  size = "sm",
  className,
  title,
  pending,
  ...rest
}: BtnProps) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled || pending}
      title={title}
      aria-label={rest["aria-label"]}
      aria-keyshortcuts={rest["aria-keyshortcuts"]}
      className={cn(
        "inline-flex shrink-0 items-center justify-center gap-1.5 whitespace-nowrap rounded-full border font-medium",
        "transition-[background-color,border-color,color,box-shadow] duration-150",
        "disabled:cursor-not-allowed disabled:opacity-45",
        size === "xs" && "h-7 px-2.5 text-[11.5px]",
        size === "sm" && "h-8 px-3 text-[12.5px]",
        size === "md" && "h-10 px-4 text-sm",
        tone === "default" && "border-line-strong bg-white/[0.03] text-fg hover:border-white/20 hover:bg-white/[0.07]",
        tone === "primary" &&
          "border-transparent bg-[linear-gradient(135deg,#f2fdff_0%,#9fe9ff_38%,#5b8cff_100%)] text-bg-deep shadow-[0_6px_18px_-8px_rgba(89,217,255,0.6)] hover:shadow-[0_8px_24px_-8px_rgba(89,217,255,0.85)]",
        tone === "danger" && "border-red-400/25 bg-red-400/[0.06] text-red-300 hover:bg-red-400/[0.12]",
        tone === "amber" && "border-amber/30 bg-amber/[0.08] text-amber hover:bg-amber/[0.14]",
        tone === "ghost" && "border-transparent text-fg-muted hover:bg-white/[0.05] hover:text-fg",
        className,
      )}
    >
      {pending && <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />}
      {children}
    </button>
  );
}

/* ------------------------------------------------------------------ */
/* Page chrome                                                         */
/* ------------------------------------------------------------------ */
export function PageHeader({
  eyebrow,
  title,
  lead,
  actions,
  className,
}: {
  eyebrow?: ReactNode;
  title: ReactNode;
  lead?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <header className={cn("flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between", className)}>
      <div className="min-w-0">
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1 className="mt-2 text-[26px] font-semibold leading-tight text-gradient-ice sm:text-3xl">{title}</h1>
        {lead && <p className="mt-2 max-w-2xl text-sm text-fg-muted">{lead}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

export function Panel({
  title,
  sub,
  actions,
  children,
  className,
  bodyClassName,
  id,
}: {
  title?: ReactNode;
  sub?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  id?: string;
}) {
  return (
    <section id={id} className={cn("surface-card relative rounded-2xl", className)}>
      {(title || actions) && (
        <div className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-4 py-3.5 sm:px-5">
          <div className="min-w-0">
            {title && <h2 className="text-[14px] font-medium text-fg">{title}</h2>}
            {sub && <p className="mt-0.5 text-xs text-fg-dim">{sub}</p>}
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </div>
      )}
      <div className={cn("p-4 sm:p-5", bodyClassName)}>{children}</div>
    </section>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn("block rounded-md bg-white/[0.06] animate-pulse motion-reduce:animate-none", className)}
    />
  );
}

export function LoadingBlock({ rows = 4, label = "Loading" }: { rows?: number; label?: string }) {
  return (
    <div role="status" aria-label={label} className="flex flex-col gap-3 py-2">
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className={cn("h-9", i % 3 === 1 ? "w-4/5" : i % 3 === 2 ? "w-3/5" : "w-full")} />
      ))}
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  children,
  action,
  className,
}: {
  icon?: ReactNode;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center px-4 py-12 text-center", className)}>
      <span className="grid h-11 w-11 place-items-center rounded-full border border-cyan/20 bg-cyan/[0.06] text-cyan">
        {icon ?? <Inbox className="h-5 w-5" strokeWidth={1.75} aria-hidden="true" />}
      </span>
      <h3 className="mt-4 text-[15px] font-medium text-fg">{title}</h3>
      {children && <div className="mt-1.5 max-w-md text-sm text-fg-muted">{children}</div>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

/** Error panel. A 501 reads as "not live yet" rather than a failure. */
export function ErrorState({ error, onRetry, className }: { error: unknown; onRetry?: () => void; className?: string }) {
  const notLive = error instanceof ApiError && error.status === 501;
  return (
    <div
      role="alert"
      className={cn(
        "flex flex-col items-center gap-3 rounded-xl border px-4 py-10 text-center",
        notLive ? "border-line bg-white/[0.02]" : "border-amber/25 bg-amber/[0.04]",
        className,
      )}
    >
      <span
        className={cn(
          "grid h-10 w-10 place-items-center rounded-full border",
          notLive ? "border-line-strong text-fg-muted" : "border-amber/30 text-amber",
        )}
      >
        {notLive ? (
          <Construction className="h-4.5 w-4.5" strokeWidth={1.75} aria-hidden="true" />
        ) : (
          <AlertTriangle className="h-4.5 w-4.5" strokeWidth={1.75} aria-hidden="true" />
        )}
      </span>
      <p className="text-sm text-fg">{notLive ? "Coming online" : "Couldn't load this"}</p>
      <p className="max-w-sm text-xs text-fg-muted">{errorMessage(error)}</p>
      {onRetry && (
        <Btn size="xs" onClick={onRetry}>
          <RefreshCw className="h-3 w-3" aria-hidden="true" /> Retry
        </Btn>
      )}
    </div>
  );
}

/**
 * A failed request's message, plus any per-field messages from the API.
 * Pass `shownInline` with the field names the form already shows next to its
 * inputs (matched like `ApiError.fieldError`) so they are not repeated here.
 */
export function InlineError({
  error,
  className,
  shownInline = [],
}: {
  error: unknown;
  className?: string;
  shownInline?: readonly string[];
}) {
  if (!error) return null;
  const rest =
    error instanceof ApiError
      ? Object.entries(error.fields).filter(
          ([k]) => !shownInline.some((n) => k === n || k.startsWith(`${n}.`)),
        )
      : [];
  return (
    <div role="alert" className={cn("flex items-start gap-1.5 text-xs text-amber", className)}>
      <AlertTriangle className="mt-px h-3.5 w-3.5 shrink-0" aria-hidden="true" />
      <div className="min-w-0">
        <p>{errorMessage(error)}</p>
        {rest.length > 0 && (
          <ul className="mt-1 flex flex-col gap-0.5">
            {rest.map(([k, v]) => (
              <li key={k}>
                {k && <span className="text-fg-muted">{fieldLabel(k)}: </span>}
                {v}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Pills                                                               */
/* ------------------------------------------------------------------ */
export type Tone = "cyan" | "green" | "amber" | "red" | "neutral" | "blue";

const TONES: Record<Tone, string> = {
  cyan: "border-cyan/25 bg-cyan/[0.07] text-cyan",
  green: "border-green/30 bg-green/[0.08] text-green",
  amber: "border-amber/30 bg-amber/[0.08] text-amber",
  red: "border-red-400/30 bg-red-400/[0.08] text-red-300",
  blue: "border-blue/30 bg-blue/[0.08] text-[#9db8ff]",
  neutral: "border-line-strong bg-white/[0.03] text-fg-muted",
};

export function Pill({
  tone = "neutral",
  children,
  className,
  dot,
}: {
  tone?: Tone;
  children: ReactNode;
  className?: string;
  dot?: boolean;
}) {
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border px-2 py-0.5 font-mono text-[10.5px] tracking-[0.06em]",
        TONES[tone],
        className,
      )}
    >
      {dot && <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-current" />}
      {children}
    </span>
  );
}

export function RecommendedTag({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border border-cyan/35 bg-[#0c1a24] px-2 py-0.5 font-mono text-[9.5px] tracking-[0.12em] text-cyan shadow-[0_0_14px_rgba(89,217,255,0.3)]",
        className,
      )}
    >
      RECOMMENDED
    </span>
  );
}

/* ------------------------------------------------------------------ */
/* Dialog                                                              */
/* ------------------------------------------------------------------ */
export function Dialog({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  wide,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  wide?: boolean;
}) {
  const titleId = useId();
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement as HTMLElement | null;
    const node = ref.current;
    const first = node?.querySelector<HTMLElement>("input, textarea, select, button:not([data-close])");
    first?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      prev?.focus?.();
    };
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center p-0 sm:items-center sm:p-6">
      <button
        type="button"
        aria-label="Close dialog"
        data-close
        className="absolute inset-0 bg-bg-deep/75 backdrop-blur-sm"
        onClick={onClose}
      />
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={cn(
          "glass-strong relative max-h-[92dvh] w-full overflow-y-auto rounded-t-2xl shadow-shell sm:rounded-2xl",
          wide ? "sm:max-w-2xl" : "sm:max-w-md",
        )}
      >
        <div className="flex items-start justify-between gap-3 border-b border-line px-5 py-4">
          <div>
            <h2 id={titleId} className="text-[15px] font-medium text-fg">
              {title}
            </h2>
            {description && <div className="mt-1 text-xs text-fg-muted">{description}</div>}
          </div>
          <button
            type="button"
            data-close
            onClick={onClose}
            aria-label="Close"
            className="grid h-8 w-8 shrink-0 place-items-center rounded-full text-fg-dim hover:bg-white/[0.06] hover:text-fg"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
        <div className="px-5 py-4">{children}</div>
        {footer && <div className="flex flex-wrap justify-end gap-2 border-t border-line px-5 py-3.5">{footer}</div>}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Segmented control                                                   */
/* ------------------------------------------------------------------ */
export function Segmented<T extends string>({
  value,
  onChange,
  options,
  label,
  className,
}: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: ReactNode }[];
  label: string;
  className?: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className={cn("glass inline-flex rounded-full p-1", className)}>
      {options.map((o) => {
        const selected = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={selected}
            onClick={() => onChange(o.value)}
            className={cn(
              "h-8 rounded-full px-3.5 text-[12.5px] font-medium transition-colors duration-200",
              selected
                ? "bg-[linear-gradient(135deg,#f2fdff,#9fe9ff_45%,#5b8cff)] text-bg-deep"
                : "text-fg-muted hover:text-fg",
            )}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

/** Horizontally scrollable table wrapper that never widens the page. */
export function TableScroll({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("max-w-full overflow-x-auto overscroll-x-contain", className)}>{children}</div>;
}

export const thCls =
  "whitespace-nowrap border-b border-line px-3 pb-2.5 pt-1 text-left font-mono text-[10px] font-normal uppercase tracking-[0.14em] text-fg-dim first:pl-0 last:pr-0";
export const tdCls = "border-b border-line px-3 py-3 align-middle first:pl-0 last:pr-0";
