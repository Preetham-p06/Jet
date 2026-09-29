"use client";

import { useRef, useState, type DragEvent, type FormEvent } from "react";
import { CheckCircle2, FileUp, Loader2, UploadCloud, XCircle } from "lucide-react";
import {
  endpoints,
  type DocumentChannel,
  type ExtractionStatus,
  type SourceDocument,
} from "@/lib/api/endpoints";
import { useApi, useBoundedPoll, useMutation } from "@/lib/api/hooks";
import { cn } from "@/lib/utils";
import { useCan, useMe } from "../me-provider";
import { humanize, toLocalInput } from "../fmt";
import { Btn, Field, InlineError, Panel, Segmented, inputCls, selectCls, textareaCls } from "../ui";
import { useTrip } from "./trip-context";

const CHANNELS: DocumentChannel[] = ["pdf_upload", "email", "sms", "whatsapp", "paste", "other"];
const ACCEPT = ".pdf,.eml,.txt,.png,.jpg,.jpeg,application/pdf,message/rfc822,text/plain,image/png,image/jpeg";
/** The backend's default `max_upload_mb`; used until the API reports its own. */
export const DEFAULT_MAX_UPLOAD_MB = 15;

export const TERMINAL: ExtractionStatus[] = ["succeeded", "failed", "needs_manual"];

/** Stop auto-refreshing a pending document after this long. */
export const POLL_CEILING_MS = 3 * 60_000;
/** A pending or processing document older than this is shown as possibly stalled. */
export const STALE_PENDING_MS = 3 * 60_000;

/** Pending or processing, and uploaded more than `STALE_PENDING_MS` ago. */
export function isStalePending(doc: Pick<SourceDocument, "extraction_status" | "created_at">, now: number): boolean {
  if (TERMINAL.includes(doc.extraction_status) || !now) return false;
  const created = Date.parse(doc.created_at);
  return Number.isFinite(created) && now - created > STALE_PENDING_MS;
}

/** The upload limit from `/auth/me` once the backend reports it, else the default. */
function maxUploadMb(me: object): number {
  const v = (me as { max_upload_mb?: unknown }).max_upload_mb;
  return typeof v === "number" && v > 0 ? v : DEFAULT_MAX_UPLOAD_MB;
}

type Mode = "file" | "paste";

function guessChannel(file: File): DocumentChannel {
  const n = file.name.toLowerCase();
  if (n.endsWith(".eml")) return "email";
  if (n.endsWith(".txt")) return "sms";
  return "pdf_upload";
}

/**
 * Drop a file or paste text, tag channel/sender/received time and an operator,
 * then poll `GET /source-documents/{id}` until extraction settles.
 */
export function IngestPanel({ onSettled, onStarted }: { onSettled: () => void; onStarted: () => void }) {
  const { tripId, version } = useTrip();
  const canIngest = useCan("ingest");
  const maxMb = maxUploadMb(useMe());
  const [mode, setMode] = useState<Mode>("file");
  const [file, setFile] = useState<File | null>(null);
  const [text, setText] = useState("");
  const [channel, setChannel] = useState<DocumentChannel>("pdf_upload");
  const [sender, setSender] = useState("");
  const [subject, setSubject] = useState("");
  const [receivedAt, setReceivedAt] = useState(() => toLocalInput(new Date()));
  const [operatorId, setOperatorId] = useState("");
  const [drag, setDrag] = useState(false);
  const [fileError, setFileError] = useState<string | null>(null);
  const [tracking, setTracking] = useState<SourceDocument | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const rfq = useApi(`rfq:${tripId}`, () => endpoints.tripOperators(tripId), version);
  const ingest = useMutation((form: FormData) => endpoints.ingest(tripId, form));

  const pending = tracking && !TERMINAL.includes(tracking.extraction_status);
  const pollExpired = useBoundedPoll(
    async () => {
      if (!tracking) return;
      try {
        const d = await endpoints.sourceDocument(tracking.id);
        setTracking(d);
        if (TERMINAL.includes(d.extraction_status)) onSettled();
      } catch {
        // keep polling; transient failures are expected while the backend works
      }
    },
    1500,
    !!pending,
    { maxMs: POLL_CEILING_MS, key: tracking?.id ?? "" },
  );

  function pickFile(f: File | undefined | null) {
    setFileError(null);
    if (!f) return;
    if (f.size > maxMb * 1024 * 1024) {
      setFileError(`That file is over ${maxMb} MB.`);
      return;
    }
    setFile(f);
    setChannel(guessChannel(f));
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDrag(false);
    pickFile(e.dataTransfer.files?.[0]);
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setNotice(null);
    const form = new FormData();
    if (mode === "file") {
      if (!file) return;
      form.set("file", file);
    } else {
      if (!text.trim()) return;
      form.set("text", text);
    }
    form.set("channel", mode === "paste" && channel === "pdf_upload" ? "paste" : channel);
    if (sender.trim()) form.set("sender", sender.trim());
    if (subject.trim()) form.set("subject", subject.trim());
    if (receivedAt) form.set("received_at", new Date(receivedAt).toISOString());
    if (operatorId) form.set("operator_id", operatorId);
    const res = await ingest.run(form);
    if (!res) return;
    onStarted();
    setTracking(res.source_document);
    if (res.duplicate) setNotice("This document was already uploaded to this trip; showing the existing one.");
    else if (res.created_quote) setNotice(`New quote created for ${res.quote?.operator_name ?? "the operator"}.`);
    else if (res.quote) setNotice(`Merged into ${res.quote.operator_name}'s quote.`);
    if (TERMINAL.includes(res.source_document.extraction_status)) onSettled();
    setFile(null);
    setText("");
    setSubject("");
  }

  const ready = mode === "file" ? !!file : !!text.trim();

  return (
    <Panel
      title="Add a quote"
      sub="PDF, email (.eml), SMS or pasted text. Extraction runs automatically."
      actions={
        <Segmented
          label="Input"
          value={mode}
          onChange={(m) => {
            setMode(m);
            setChannel(m === "paste" ? "sms" : file ? guessChannel(file) : "pdf_upload");
          }}
          options={[
            { value: "file", label: "Upload" },
            { value: "paste", label: "Paste" },
          ]}
        />
      }
    >
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        {mode === "file" ? (
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDrag(true);
            }}
            onDragLeave={() => setDrag(false)}
            onDrop={onDrop}
            className={cn(
              "relative flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed px-4 py-7 text-center transition-colors",
              drag ? "border-cyan/60 bg-cyan/[0.06]" : "border-line-strong bg-white/[0.015] hover:border-white/20",
            )}
          >
            <UploadCloud className={cn("h-6 w-6", drag ? "text-cyan" : "text-fg-dim")} strokeWidth={1.6} aria-hidden="true" />
            {file ? (
              <p className="text-[13px] text-fg">
                <span className="font-mono">{file.name}</span>{" "}
                <span className="text-fg-dim">· {(file.size / 1024).toFixed(0)} KB</span>
              </p>
            ) : (
              <p className="text-[13px] text-fg-muted">Drop an operator quote here <span className="text-fg-dim">· up to {maxMb} MB</span></p>
            )}
            <Btn size="xs" onClick={() => inputRef.current?.click()}>
              <FileUp className="h-3.5 w-3.5" aria-hidden="true" /> {file ? "Choose another" : "Browse files"}
            </Btn>
            <input
              ref={inputRef}
              type="file"
              accept={ACCEPT}
              className="sr-only"
              aria-label="Quote file"
              onChange={(e) => pickFile(e.target.files?.[0])}
            />
            {fileError && <p className="text-xs text-amber">{fileError}</p>}
          </div>
        ) : (
          <Field label="Message text" htmlFor="ingest-text">
            <textarea
              id="ingest-text"
              value={text}
              onChange={(e) => setText(e.target.value)}
              className={cn(textareaCls, "min-h-[120px] font-mono text-[12.5px]")}
              placeholder="Hi it's Dan at Summit re JS184… quote is 38,900 all in, crew overnight 700 extra."
            />
          </Field>
        )}

        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Operator" htmlFor="ingest-op" hint="Pick from the RFQ list, or let JetStream match it.">
            <select id="ingest-op" value={operatorId} onChange={(e) => setOperatorId(e.target.value)} className={selectCls}>
              <option value="">Auto-detect from document</option>
              {(rfq.data?.items ?? []).map((r) => (
                <option key={r.id} value={r.operator_id}>
                  {r.operator_name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Channel" htmlFor="ingest-channel">
            <select
              id="ingest-channel"
              value={channel}
              onChange={(e) => setChannel(e.target.value as DocumentChannel)}
              className={selectCls}
            >
              {CHANNELS.map((c) => (
                <option key={c} value={c}>
                  {c === "pdf_upload" ? "PDF upload" : humanize(c)}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Sender" htmlFor="ingest-sender">
            <input
              id="ingest-sender"
              value={sender}
              onChange={(e) => setSender(e.target.value)}
              className={inputCls}
              placeholder="dan@summit.example or +1 555…"
            />
          </Field>
          <Field label="Received at" htmlFor="ingest-at">
            <input
              id="ingest-at"
              type="datetime-local"
              value={receivedAt}
              onChange={(e) => setReceivedAt(e.target.value)}
              className={cn(inputCls, "[color-scheme:dark]")}
            />
          </Field>
          {channel === "email" && (
            <Field label="Subject" htmlFor="ingest-subject" className="sm:col-span-2">
              <input id="ingest-subject" value={subject} onChange={(e) => setSubject(e.target.value)} className={inputCls} />
            </Field>
          )}
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3">
          <InlineError error={ingest.error} />
          <Btn
            type="submit"
            tone="primary"
            size="md"
            className="ml-auto"
            disabled={!ready || !canIngest}
            pending={ingest.pending}
            title={canIngest ? undefined : "Your role can't ingest quotes"}
          >
            {ingest.pending ? "Uploading…" : "Extract quote"}
          </Btn>
        </div>

        {tracking && <TrackingRow doc={tracking} notice={notice} stalled={!!pending && pollExpired} />}
      </form>
    </Panel>
  );
}

function TrackingRow({ doc, notice, stalled }: { doc: SourceDocument; notice: string | null; stalled: boolean }) {
  const s = doc.extraction_status;
  const done = s === "succeeded";
  const bad = s === "failed" || s === "needs_manual";
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        "flex items-start gap-3 rounded-xl border px-3.5 py-3 text-[12.5px]",
        done ? "border-green/25 bg-green/[0.05]" : bad ? "border-amber/30 bg-amber/[0.05]" : "border-cyan/25 bg-cyan/[0.04]",
      )}
    >
      {done ? (
        <CheckCircle2 className="mt-px h-4 w-4 shrink-0 text-green" aria-hidden="true" />
      ) : bad ? (
        <XCircle className="mt-px h-4 w-4 shrink-0 text-amber" aria-hidden="true" />
      ) : (
        <Loader2 className="mt-px h-4 w-4 shrink-0 animate-spin text-cyan" aria-hidden="true" />
      )}
      <div className="min-w-0 flex-1">
        <p className="text-fg">
          <span className="font-mono">{doc.original_filename ?? humanize(doc.kind)}</span> ·{" "}
          {done ? "Extracted" : bad ? humanize(s) : <span className="shimmer-text">{humanize(s)}…</span>}
          {doc.extractor && <span className="text-fg-dim"> · {doc.extractor}</span>}
          {doc.processing_ms != null && <span className="text-fg-dim"> · {(doc.processing_ms / 1000).toFixed(1)}s</span>}
        </p>
        {doc.extraction_error && <p className="mt-0.5 text-fg-muted">{doc.extraction_error}</p>}
        {notice && <p className="mt-0.5 text-fg-muted">{notice}</p>}
        {stalled && (
          <p className="mt-0.5 text-fg-muted">
            Still processing after 3 minutes. Auto-refresh has stopped; check Source documents below, where you can reprocess it.
          </p>
        )}
      </div>
    </div>
  );
}
