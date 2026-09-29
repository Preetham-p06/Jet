"use client";

import { useState } from "react";
import { ExternalLink, FileText, Mail, MessageSquare, RotateCw, Table2 } from "lucide-react";
import { endpoints, sourceFileUrl, type SourceDocument } from "@/lib/api/endpoints";
import { useApi, useMutation, usePoll } from "@/lib/api/hooks";
import { cn } from "@/lib/utils";
import { useCan } from "../me-provider";
import { fmtDateTime, humanize } from "../fmt";
import { Btn, EmptyState, ErrorState, InlineError, LoadingBlock, Panel, Pill, Segmented } from "../ui";
import { ComparisonCards, ComparisonTable } from "./comparison";
import { IngestPanel, TERMINAL } from "./ingest-panel";
import { LiveProcessingLog } from "./processing-log";
import { useTrip } from "./trip-context";

export function QuotesTab() {
  const { tripId, version, bump } = useTrip();
  const [view, setView] = useState<"table" | "cards">("table");
  const [live, setLive] = useState(false);
  const comparison = useApi(`comparison:${tripId}`, () => endpoints.comparison(tripId), version);
  const docs = useApi(`docs:${tripId}`, () => endpoints.sourceDocuments(tripId), version);

  const anyPending = (docs.data?.items ?? []).some((d) => !TERMINAL.includes(d.extraction_status));
  // Background-mode extraction: keep the documents list fresh until all settle.
  usePoll(docs.reload, 2500, anyPending);

  return (
    <div className="flex flex-col gap-5">
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        <IngestPanel
          onStarted={() => setLive(true)}
          onSettled={() => {
            setLive(false);
            bump();
          }}
        />
        <LiveProcessingLog tripId={tripId} live={live || anyPending} className="min-h-[260px]" maxHeight={420} />
      </div>

      <Panel
        title="Quote comparison"
        sub="Every quote normalized to true cost: stated fees, inclusions, estimates and unstated charges."
        actions={
          <Segmented
            label="Comparison view"
            value={view}
            onChange={setView}
            options={[
              { value: "table", label: "Table" },
              { value: "cards", label: "Cards" },
            ]}
          />
        }
        className={cn(comparison.refreshing && "[&_table]:opacity-70")}
      >
        {comparison.loading ? (
          <LoadingBlock rows={5} label="Loading comparison" />
        ) : comparison.error && !comparison.data ? (
          <ErrorState error={comparison.error} onRetry={comparison.reload} />
        ) : !comparison.data?.rows.length ? (
          <EmptyState icon={<Table2 className="h-5 w-5" strokeWidth={1.75} aria-hidden="true" />} title="No quotes yet">
            Upload an operator quote above. Each one lands here with every fee normalized.
          </EmptyState>
        ) : view === "table" ? (
          <ComparisonTable data={comparison.data} tripId={tripId} />
        ) : (
          <ComparisonCards data={comparison.data} />
        )}
      </Panel>

      <Panel title="Source documents" sub="Every file and message behind these quotes." bodyClassName="p-0 sm:p-0">
        {docs.loading ? (
          <div className="p-5">
            <LoadingBlock rows={3} />
          </div>
        ) : docs.error && !docs.data ? (
          <div className="p-5">
            <ErrorState error={docs.error} onRetry={docs.reload} />
          </div>
        ) : !docs.data?.items.length ? (
          <p className="px-5 py-6 text-center text-sm text-fg-dim">No documents uploaded yet.</p>
        ) : (
          <ul className="divide-y divide-line">
            {docs.data.items.map((d) => (
              <DocRow key={d.id} doc={d} onChanged={bump} />
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}

function DocIcon({ kind }: { kind: SourceDocument["kind"] }) {
  const cls = "h-4 w-4 text-fg-dim";
  if (kind === "email") return <Mail className={cls} aria-hidden="true" />;
  if (kind === "sms" || kind === "whatsapp" || kind === "text") return <MessageSquare className={cls} aria-hidden="true" />;
  return <FileText className={cls} aria-hidden="true" />;
}

function DocRow({ doc, onChanged }: { doc: SourceDocument; onChanged: () => void }) {
  const canReprocess = useCan("field.review");
  const reprocess = useMutation(() => endpoints.reprocess(doc.id));
  const s = doc.extraction_status;
  const tone = s === "succeeded" ? "green" : s === "failed" || s === "needs_manual" ? "amber" : "cyan";
  return (
    <li className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3 sm:px-5">
      <DocIcon kind={doc.kind} />
      <div className="min-w-0 flex-1">
        <a
          href={sourceFileUrl(doc.id)}
          target="_blank"
          rel="noreferrer"
          className="inline-flex max-w-full items-center gap-1.5 truncate font-mono text-[12.5px] text-fg hover:text-cyan"
        >
          {doc.original_filename ?? `${humanize(doc.kind)} message`}
          <ExternalLink className="h-3 w-3 shrink-0 text-fg-dim" aria-hidden="true" />
        </a>
        <p className="truncate text-xs text-fg-dim">
          {humanize(doc.channel)}
          {doc.sender && ` · ${doc.sender}`} · received {fmtDateTime(doc.received_at ?? doc.created_at)}
          {doc.page_count ? ` · ${doc.page_count} p` : ""}
          {doc.is_scanned ? " · scanned" : ""}
        </p>
        {doc.extraction_error && <p className="mt-0.5 text-xs text-amber">{doc.extraction_error}</p>}
      </div>
      <div className="flex items-center gap-2">
        {doc.intent && doc.intent !== "quote" && <Pill>{humanize(doc.intent)}</Pill>}
        {doc.extractor && <Pill>{doc.extractor}</Pill>}
        <Pill tone={tone} dot>
          {humanize(s)}
        </Pill>
        {canReprocess && TERMINAL.includes(s) && (
          <Btn
            size="xs"
            tone="ghost"
            aria-label="Reprocess document"
            title="Re-extract"
            pending={reprocess.pending}
            onClick={async () => {
              if (await reprocess.run()) onChanged();
            }}
          >
            {!reprocess.pending && <RotateCw className="h-3.5 w-3.5" aria-hidden="true" />}
          </Btn>
        )}
      </div>
      {reprocess.error && <InlineError error={reprocess.error} className="w-full" />}
    </li>
  );
}
