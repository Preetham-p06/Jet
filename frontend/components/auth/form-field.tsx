import type { InputHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

type Props = InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  hint?: string;
};

export const inputClass = cn(
  "h-11 w-full rounded-xl border border-line bg-white/[0.03] px-3.5 text-sm text-fg",
  "placeholder:text-fg-dim transition-[border-color,background-color,box-shadow] duration-200",
  "hover:border-line-strong focus:border-cyan/45 focus:bg-white/[0.05] focus:outline-none focus:ring-2 focus:ring-cyan/15",
  "disabled:opacity-60",
);

export function FormField({ label, hint, id, className, ...input }: Props) {
  const fieldId = id ?? input.name;
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={fieldId} className="text-[13px] font-medium text-fg-muted">
        {label}
      </label>
      <input id={fieldId} className={cn(inputClass, className)} {...input} />
      {hint && <p className="text-xs text-fg-dim">{hint}</p>}
    </div>
  );
}
