"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight } from "lucide-react";
import { ApiError, api } from "@/lib/api/client";
import { fieldLabel } from "@/lib/api/errors";
import type { Me } from "@/lib/api/types";
import { GlowButton } from "@/components/ui/glow-button";
import { FormField } from "./form-field";
import { FormError } from "./form-error";
import { authErrorMessage } from "./auth-errors";

/** Mirrors `MIN_PASSWORD_LENGTH` in `backend/app/security/passwords.py`. */
const MIN_PASSWORD = 10;
const FIELDS = ["workspace_name", "full_name", "email", "password"] as const;
type FieldName = (typeof FIELDS)[number];

export function SignupForm({ next }: { next: string | null }) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<FieldName, string>>>({});

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const data = new FormData(e.currentTarget);
    const body = {
      workspace_name: String(data.get("workspace_name") ?? "").trim(),
      full_name: String(data.get("full_name") ?? "").trim(),
      email: String(data.get("email") ?? "").trim(),
      password: String(data.get("password") ?? ""),
    };
    if (body.password.length < MIN_PASSWORD) {
      setError(`Use at least ${MIN_PASSWORD} characters for your password.`);
      return;
    }
    setPending(true);
    setError(null);
    setFieldErrors({});
    try {
      await api<Me>("/auth/signup", { method: "POST", json: body, redirectOn401: false });
      router.replace(next ?? "/trips");
      router.refresh();
    } catch (err) {
      let message = authErrorMessage(err, "signup");
      if (err instanceof ApiError) {
        const inline: Partial<Record<FieldName, string>> = {};
        for (const f of FIELDS) inline[f] = err.fieldError(f) ?? undefined;
        setFieldErrors(inline);
        // Anything the form has no input for goes in the banner.
        const rest = Object.entries(err.fields).filter(([k]) => !FIELDS.some((f) => k === f || k.startsWith(`${f}.`)));
        if (rest.length) message += ` ${rest.map(([k, v]) => (k ? `${fieldLabel(k)}: ${v}` : v)).join("; ")}`;
      }
      setError(message);
      setPending(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4">
      <FormError message={error} />
      <FormField
        label="Brokerage name"
        name="workspace_name"
        autoComplete="organization"
        placeholder="Meridian Air Partners"
        error={fieldErrors.workspace_name}
        required
        autoFocus
        disabled={pending}
      />
      <FormField
        label="Your name"
        name="full_name"
        autoComplete="name"
        placeholder="Alex Morgan"
        error={fieldErrors.full_name}
        required
        disabled={pending}
      />
      <FormField
        label="Work email"
        name="email"
        type="email"
        autoComplete="email"
        placeholder="you@brokerage.com"
        error={fieldErrors.email}
        required
        disabled={pending}
      />
      <FormField
        label="Password"
        name="password"
        type="password"
        autoComplete="new-password"
        minLength={MIN_PASSWORD}
        hint={`At least ${MIN_PASSWORD} characters.`}
        error={fieldErrors.password}
        required
        disabled={pending}
      />
      <GlowButton
        type="submit"
        size="lg"
        className="mt-2 w-full"
        disabled={pending}
        icon={pending ? undefined : <ArrowRight className="h-4 w-4" />}
      >
        {pending ? "Creating workspace…" : "Create workspace"}
      </GlowButton>
    </form>
  );
}
