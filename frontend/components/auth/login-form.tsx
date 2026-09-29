"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight } from "lucide-react";
import { api } from "@/lib/api/client";
import type { Me } from "@/lib/api/types";
import { GlowButton } from "@/components/ui/glow-button";
import { FormField } from "./form-field";
import { FormError } from "./form-error";
import { authErrorMessage } from "./auth-errors";

export function LoginForm({ next }: { next: string | null }) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const data = new FormData(e.currentTarget);
    setPending(true);
    setError(null);
    try {
      await api<Me>("/auth/login", {
        method: "POST",
        json: { email: String(data.get("email") ?? "").trim(), password: String(data.get("password") ?? "") },
        redirectOn401: false,
      });
      router.replace(next ?? "/trips");
      router.refresh();
    } catch (err) {
      setError(authErrorMessage(err, "login"));
      setPending(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4">
      <FormError message={error} />
      <FormField
        label="Work email"
        name="email"
        type="email"
        autoComplete="email"
        placeholder="you@brokerage.com"
        required
        autoFocus
        disabled={pending}
      />
      <FormField
        label="Password"
        name="password"
        type="password"
        autoComplete="current-password"
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
        {pending ? "Signing in…" : "Sign in"}
      </GlowButton>
    </form>
  );
}
