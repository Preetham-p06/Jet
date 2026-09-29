import type { Metadata } from "next";
import Link from "next/link";
import { AuthCard } from "@/components/auth/auth-card";
import { LoginForm } from "@/components/auth/login-form";
import { safeNext } from "@/lib/safe-next";

export const metadata: Metadata = {
  title: "Log in",
  robots: { index: false, follow: false },
};

export default async function LoginPage(props: PageProps<"/login">) {
  const next = safeNext((await props.searchParams).next);
  const signupHref = next ? `/signup?next=${encodeURIComponent(next)}` : "/signup";
  return (
    <AuthCard
      eyebrow="Broker workspace"
      title="Welcome back"
      subtitle="Sign in to compare quotes, clear the review queue and send proposals."
      footer={
        <>
          New to JetStream?{" "}
          <Link href={signupHref} className="font-medium text-cyan transition-colors hover:text-ice">
            Create a workspace
          </Link>
        </>
      }
    >
      <LoginForm next={next} />
    </AuthCard>
  );
}
