"use client";

import { endpoints } from "@/lib/api/endpoints";
import { useApi } from "@/lib/api/hooks";
import { useCan } from "../me-provider";
import { AuditTable } from "../audit-table";
import { ErrorState, LoadingBlock, Panel } from "../ui";
import { LiveProcessingLog } from "./processing-log";
import { useTrip } from "./trip-context";

export function ActivityTab() {
  const { tripId, version } = useTrip();
  const canAudit = useCan("audit.view");
  const audit = useApi(canAudit ? `audit:${tripId}` : null, () => endpoints.auditEvents({ trip_id: tripId, limit: 100 }), version);

  return (
    <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <div className="min-w-0">
        <h2 className="mb-3 text-[14px] font-medium text-fg">Processing log</h2>
        <LiveProcessingLog tripId={tripId} live={false} maxHeight={640} />
      </div>
      <div className="min-w-0">
        <h2 className="mb-3 text-[14px] font-medium text-fg">Audit trail</h2>
        {!canAudit ? (
          <Panel>
            <p className="text-sm text-fg-dim">The audit trail is visible to brokers and admins.</p>
          </Panel>
        ) : audit.loading ? (
          <Panel>
            <LoadingBlock rows={5} />
          </Panel>
        ) : audit.error && !audit.data ? (
          <ErrorState error={audit.error} onRetry={audit.reload} />
        ) : (
          <Panel bodyClassName="p-0 sm:p-0">
            <AuditTable events={audit.data?.items ?? []} compact />
          </Panel>
        )}
      </div>
    </div>
  );
}
