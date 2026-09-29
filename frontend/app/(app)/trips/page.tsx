import type { Metadata } from "next";
import { PlaneTakeoff } from "lucide-react";
import { GlassCard } from "@/components/ui/glass-card";
import { verifySession } from "@/lib/dal";

export const metadata: Metadata = { title: "Trips" };

export default async function TripsPage() {
  const me = await verifySession();
  const firstName = me.user.full_name.split(/\s+/)[0] ?? "";

  return (
    <div className="mx-auto w-full max-w-6xl">
      <header className="flex flex-col gap-2">
        <p className="eyebrow">{me.workspace.name}</p>
        <h1 className="text-3xl font-semibold text-gradient-ice">Trips</h1>
        <p className="text-sm text-fg-muted">
          {firstName ? `Welcome back, ${firstName}. ` : ""}Every open trip, its operator quotes and the true cost
          recommendation.
        </p>
      </header>

      <GlassCard edge className="mt-8 flex flex-col items-center px-6 py-16 text-center">
        <span className="grid h-12 w-12 place-items-center rounded-full border border-cyan/20 bg-cyan/[0.06] text-cyan">
          <PlaneTakeoff className="h-5 w-5" strokeWidth={1.75} aria-hidden="true" />
        </span>
        <h2 className="mt-5 text-lg font-medium text-fg">Trips will load here</h2>
        <p className="mt-2 max-w-md text-sm text-fg-muted">
          The trip list, quote comparison and review queue arrive with the dashboard package.
        </p>
      </GlassCard>
    </div>
  );
}
