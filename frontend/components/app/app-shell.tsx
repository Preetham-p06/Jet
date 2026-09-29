"use client";

import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { LogOut, Menu, X } from "lucide-react";
import { api } from "@/lib/api/client";
import type { Me } from "@/lib/api/types";
import { cn } from "@/lib/utils";
import { LogoMark } from "@/components/ui/logo";
import { MeProvider } from "./me-provider";
import { isActive, visibleNav } from "./nav";

const ROLE_LABEL: Record<string, string> = {
  admin: "Admin",
  broker: "Broker",
  assistant: "Assistant",
};

function initials(name: string) {
  return (
    name
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((p) => p[0]?.toUpperCase())
      .join("") || "?"
  );
}

/** Authenticated chrome: sidebar (desktop), top bar + drawer (mobile), and `MeProvider`. */
export function AppShell({ me, children }: { me: Me; children: ReactNode }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  // Close the drawer on navigation.
  const [lastPath, setLastPath] = useState(pathname);
  if (lastPath !== pathname) {
    setLastPath(pathname);
    setOpen(false);
  }

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <MeProvider me={me}>
      <div aria-hidden="true" className="pointer-events-none fixed inset-0 z-0">
        <div className="absolute inset-0 bg-[radial-gradient(90%_60%_at_60%_-10%,#0e1624_0%,#080b10_55%,#05070a_100%)]" />
        <div className="absolute -right-[10%] -top-[25%] h-[60vh] w-[50vw] rounded-full bg-[radial-gradient(circle,rgba(91,140,255,0.10)_0%,rgba(91,140,255,0)_60%)] blur-3xl" />
      </div>

      <div className="relative z-10 flex min-h-dvh flex-1">
        {/* Desktop sidebar */}
        <aside className="sticky top-0 hidden h-dvh w-[248px] shrink-0 flex-col border-r border-line bg-bg-deep/40 backdrop-blur-xl lg:flex">
          <Sidebar me={me} pathname={pathname} logoId="js-mark-grad-sidebar" />
        </aside>

        {/* Mobile top bar */}
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-line bg-bg-deep/80 px-4 backdrop-blur-xl lg:hidden">
            <Link href="/trips" className="inline-flex items-center gap-2">
              <LogoMark className="h-5 w-5" gradientId="js-mark-grad-topbar" />
              <span className="text-[14px] font-semibold tracking-[-0.02em]">JetStream</span>
            </Link>
            <button
              type="button"
              aria-label={open ? "Close navigation" : "Open navigation"}
              aria-expanded={open}
              aria-controls="app-drawer"
              onClick={() => setOpen((o) => !o)}
              className="grid h-10 w-10 place-items-center rounded-full text-fg-muted transition-colors hover:bg-white/[0.06] hover:text-fg"
            >
              {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </button>
          </header>

          {open && (
            <div className="fixed inset-0 z-40 lg:hidden">
              <button
                type="button"
                aria-label="Close navigation"
                className="absolute inset-0 bg-bg-deep/70 backdrop-blur-sm"
                onClick={() => setOpen(false)}
              />
              <aside
                id="app-drawer"
                className="absolute inset-y-0 left-0 flex w-[280px] max-w-[85vw] flex-col border-r border-line bg-[rgba(9,13,19,0.94)] shadow-shell backdrop-blur-xl"
              >
                <Sidebar me={me} pathname={pathname} logoId="js-mark-grad-drawer" />
              </aside>
            </div>
          )}

          <main id="main" className="relative flex-1 px-4 py-6 sm:px-6 lg:px-10 lg:py-10">
            {children}
          </main>
        </div>
      </div>
    </MeProvider>
  );
}

function Sidebar({ me, pathname, logoId }: { me: Me; pathname: string; logoId: string }) {
  const items = visibleNav(me.capabilities);
  const role = me.user.role ?? me.role;

  return (
    <>
      <div className="flex h-16 items-center gap-2.5 px-5">
        <LogoMark gradientId={logoId} />
        <span className="text-[15px] font-semibold tracking-[-0.02em] text-fg">JetStream</span>
        <span className="rounded-md border border-line px-1.5 py-px font-mono text-[10px] tracking-[0.12em] text-fg-dim">
          AI
        </span>
      </div>

      <div className="mx-3 mb-4 rounded-xl border border-line bg-white/[0.02] px-3 py-2.5">
        <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-fg-dim">Workspace</p>
        <p className="mt-1 truncate text-sm font-medium text-fg" title={me.workspace.name}>
          {me.workspace.name}
        </p>
      </div>

      <nav aria-label="Primary" className="flex-1 overflow-y-auto px-3">
        <ul className="flex flex-col gap-0.5">
          {items.map(({ href, label, icon: Icon }) => {
            const active = isActive(pathname, href);
            return (
              <li key={href}>
                <Link
                  href={href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "group relative flex h-10 items-center gap-3 rounded-lg px-3 text-sm transition-colors duration-150",
                    active
                      ? "bg-white/[0.06] text-fg"
                      : "text-fg-muted hover:bg-white/[0.035] hover:text-fg",
                  )}
                >
                  {active && (
                    <span
                      aria-hidden="true"
                      className="absolute inset-y-2 left-0 w-[2px] rounded-full bg-[linear-gradient(180deg,var(--color-cyan),var(--color-blue))] shadow-[0_0_12px_rgba(89,217,255,0.6)]"
                    />
                  )}
                  <Icon
                    className={cn("h-4 w-4 shrink-0", active ? "text-cyan" : "text-fg-dim group-hover:text-fg-muted")}
                    strokeWidth={1.75}
                    aria-hidden="true"
                  />
                  {label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      <div className="border-t border-line p-3">
        <div className="flex items-center gap-3 rounded-xl px-2 py-2">
          <span
            aria-hidden="true"
            className="grid h-9 w-9 shrink-0 place-items-center rounded-full border border-cyan/20 bg-[linear-gradient(135deg,rgba(89,217,255,0.16),rgba(91,140,255,0.10))] font-mono text-[12px] text-ice"
          >
            {initials(me.user.full_name)}
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-fg" title={me.user.full_name}>
              {me.user.full_name}
            </p>
            <p className="truncate text-xs text-fg-dim">{role ? (ROLE_LABEL[role] ?? role) : me.user.email}</p>
          </div>
          <LogoutButton />
        </div>
      </div>
    </>
  );
}

function LogoutButton() {
  const router = useRouter();
  const [pending, setPending] = useState(false);

  async function logout() {
    setPending(true);
    try {
      await api("/auth/logout", { method: "POST", redirectOn401: false });
    } catch {
      // Already signed out or backend unreachable: still leave the app.
    }
    router.replace("/login");
    router.refresh();
  }

  return (
    <button
      type="button"
      onClick={logout}
      disabled={pending}
      aria-label="Log out"
      title="Log out"
      className="grid h-9 w-9 shrink-0 place-items-center rounded-full text-fg-dim transition-colors hover:bg-white/[0.06] hover:text-fg disabled:opacity-50"
    >
      <LogOut className="h-4 w-4" strokeWidth={1.75} />
    </button>
  );
}
