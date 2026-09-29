import { AlertTriangle } from "lucide-react";

export function FormError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div
      role="alert"
      className="flex items-start gap-2.5 rounded-xl border border-amber/30 bg-amber/[0.08] px-3.5 py-3 text-[13px] leading-snug text-amber"
    >
      <AlertTriangle className="mt-px h-4 w-4 shrink-0" strokeWidth={2.25} aria-hidden="true" />
      <span>{message}</span>
    </div>
  );
}
