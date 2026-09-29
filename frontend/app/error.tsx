"use client";

import { RotateCw } from "lucide-react";
import { GlassCard } from "@/components/ui/glass-card";
import { GlowButton } from "@/components/ui/glow-button";

/** Root error boundary; mostly "backend unreachable" from `verifySession()`. */
export default function RootError({ error, retry }: { error: Error & { digest?: string }; retry: () => void }) {
  return (
    <main id="main" className="flex min-h-dvh flex-1 items-center justify-center px-4 py-16">
      <GlassCard glass edge className="shadow-shell w-full max-w-[440px] p-8 text-center">
        <p className="eyebrow">Something went wrong</p>
        <h1 className="mt-3 text-xl font-semibold text-gradient-ice">We couldn&apos;t load this page</h1>
        <p className="mt-2 text-sm text-fg-muted">
          JetStream may be temporarily unreachable. Try again in a moment.
        </p>
        {error.digest && <p className="tabular mt-4 font-mono text-[11px] text-fg-dim">Ref {error.digest}</p>}
        <div className="mt-6 flex justify-center gap-2">
          <GlowButton size="sm" onClick={retry} icon={<RotateCw className="h-3.5 w-3.5" />}>
            Try again
          </GlowButton>
          <GlowButton size="sm" variant="ghost" href="/">
            Home
          </GlowButton>
        </div>
      </GlassCard>
    </main>
  );
}
