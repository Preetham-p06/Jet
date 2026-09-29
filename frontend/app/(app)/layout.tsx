import type { Metadata } from "next";
import { AppShell } from "@/components/app/app-shell";
import { verifySession } from "@/lib/dal";

export const metadata: Metadata = {
  robots: { index: false, follow: false },
};

/**
 * Authenticated area. `verifySession()` is the real auth check (proxy.ts is
 * only optimistic). Layouts don't re-render on client navigation, so pages
 * that read protected data should call `verifySession()` too; it's cached per
 * request, so that costs no extra `/auth/me` call.
 */
export default async function AppLayout({ children }: LayoutProps<"/">) {
  const me = await verifySession();
  return <AppShell me={me}>{children}</AppShell>;
}
