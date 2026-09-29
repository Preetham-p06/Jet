import type { ReactNode } from "react";
import { GlassCard } from "@/components/ui/glass-card";

type Props = {
  eyebrow: string;
  title: string;
  subtitle?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
};

/** Centered glass card used by login, signup and invite pages. */
export function AuthCard({ eyebrow, title, subtitle, children, footer }: Props) {
  return (
    <div className="w-full max-w-[420px]">
      <GlassCard glass edge className="shadow-shell p-6 sm:p-8">
        <p className="eyebrow">{eyebrow}</p>
        <h1 className="mt-3 text-[26px] font-semibold leading-tight text-gradient-ice">{title}</h1>
        {subtitle && <p className="mt-2 text-sm leading-relaxed text-fg-muted">{subtitle}</p>}
        <div className="mt-7">{children}</div>
      </GlassCard>
      {footer && <div className="mt-5 text-center text-sm text-fg-muted">{footer}</div>}
    </div>
  );
}
