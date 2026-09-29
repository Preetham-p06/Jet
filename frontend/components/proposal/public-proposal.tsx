"use client";

import { useState, type FormEvent } from "react";
import { ArrowRight, CheckCircle2 } from "lucide-react";
import { endpoints, type PublicProposal as ProposalData } from "@/lib/api/endpoints";
import { ApiError } from "@/lib/api/errors";
import { cn } from "@/lib/utils";
import { ClientProposal } from "./client-proposal";

/**
 * Interactive wrapper for /p/[token]: the server-rendered proposal plus an
 * Accept flow that asks for the client's name and posts to the public endpoint.
 */
export function PublicProposalView({ token, initial }: { token: string; initial: ProposalData }) {
  const [proposal, setProposal] = useState(initial);
  const [choosing, setChoosing] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const open = proposal.status === "sent";
  const accepted = proposal.accepted_option_id;

  async function accept(e: FormEvent) {
    e.preventDefault();
    if (!choosing || !name.trim()) return;
    setPending(true);
    setError(null);
    try {
      const res = await endpoints.acceptPublic(token, choosing, name.trim());
      setProposal(res);
      setChoosing(null);
    } catch (err) {
      setError(
        err instanceof ApiError && (err.status === 404 || err.status === 410)
          ? "This proposal is no longer available. Please contact your broker."
          : err instanceof ApiError && err.status === 409
            ? "This proposal was already answered."
            : "We couldn't record your choice. Please try again or contact your broker.",
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <>
      {accepted && (
        <div role="status" className="mb-8 flex items-center justify-center gap-2 rounded-2xl border border-green/30 bg-green/[0.06] px-4 py-3 text-sm text-green">
          <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
          Thank you. Your broker has your selection and will confirm the booking.
        </div>
      )}
      <ClientProposal
        proposal={proposal}
        renderAction={
          open && !accepted
            ? (id) =>
                choosing === id ? (
                  <form onSubmit={accept} className="flex flex-col gap-2">
                    <label htmlFor={`name-${id}`} className="text-[12px] text-fg-muted">
                      Your name, to confirm this option
                    </label>
                    <input
                      id={`name-${id}`}
                      autoFocus
                      required
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      autoComplete="name"
                      className="h-10 rounded-xl border border-line bg-white/[0.04] px-3 text-sm text-fg focus:border-cyan/45 focus:outline-none focus:ring-2 focus:ring-cyan/15"
                    />
                    <div className="flex gap-2">
                      <button
                        type="submit"
                        disabled={pending || !name.trim()}
                        className="inline-flex h-10 flex-1 items-center justify-center gap-1.5 rounded-full bg-[linear-gradient(135deg,#f2fdff_0%,#9fe9ff_38%,#5b8cff_100%)] text-sm font-medium text-bg-deep disabled:opacity-50"
                      >
                        {pending ? "Confirming…" : "Confirm"}
                      </button>
                      <button
                        type="button"
                        onClick={() => setChoosing(null)}
                        className="h-10 rounded-full px-3 text-sm text-fg-muted hover:text-fg"
                      >
                        Cancel
                      </button>
                    </div>
                    {error && (
                      <p role="alert" className="text-xs text-amber">
                        {error}
                      </p>
                    )}
                  </form>
                ) : (
                  <button
                    type="button"
                    onClick={() => {
                      setChoosing(id);
                      setError(null);
                    }}
                    className={cn(
                      "group inline-flex h-10 w-full items-center justify-center gap-1.5 rounded-full border text-[13px] font-medium transition-colors",
                      "border-line-strong text-fg hover:border-cyan/40 hover:text-cyan",
                    )}
                  >
                    Accept this option
                    <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" aria-hidden="true" />
                  </button>
                )
            : undefined
        }
      />
    </>
  );
}
