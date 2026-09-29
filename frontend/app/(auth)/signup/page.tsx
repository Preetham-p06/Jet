import type { Metadata } from "next";
import Link from "next/link";
import { AuthCard } from "@/components/auth/auth-card";
import { SignupForm } from "@/components/auth/signup-form";
import { safeNext } from "@/lib/safe-next";

export const metadata: Metadata = {
  title: "Create a workspace",
  robots: { index: false, follow: false },
};

export default async function SignupPage(props: PageProps<"/signup">) {
  const next = safeNext((await props.searchParams).next);
  const loginHref = next ? `/login?next=${encodeURIComponent(next)}` : "/login";
  return (
    <AuthCard
      eyebrow="Get started"
      title="Create your workspace"
      subtitle="You'll be the admin. Invite brokers and assistants once you're in."
      footer={
        <>
          Already have an account?{" "}
          <Link href={loginHref} className="font-medium text-cyan transition-colors hover:text-ice">
            Log in
          </Link>
        </>
      }
    >
      <SignupForm next={next} />
    </AuthCard>
  );
}
