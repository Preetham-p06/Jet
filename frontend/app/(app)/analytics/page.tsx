import type { Metadata } from "next";
import { AnalyticsView } from "@/components/app/analytics/analytics-view";
import { EmptyState, PageHeader } from "@/components/app/ui";
import { verifySession } from "@/lib/dal";

export const metadata: Metadata = { title: "Analytics" };

export default async function AnalyticsPage() {
  const me = await verifySession();
  const allowed = me.capabilities.includes("analytics.view");
  return (
    <div className="mx-auto w-full max-w-[1320px]">
      <PageHeader
        eyebrow="Workspace intelligence"
        title="Analytics"
        lead="Quote flow, operator responsiveness, true cost and the fees operators leave out."
      />
      {allowed ? (
        <AnalyticsView />
      ) : (
        <EmptyState className="mt-8" title="Brokers and admins only">
          Ask a workspace admin if you need access to analytics.
        </EmptyState>
      )}
    </div>
  );
}
