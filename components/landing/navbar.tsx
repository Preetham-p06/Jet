"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, motion, useMotionValueEvent, useScroll } from "motion/react";
import { ArrowRight, Menu, X } from "lucide-react";
import { Logo } from "@/components/ui/logo";
import { GlowButton } from "@/components/ui/glow-button";
import { CONTACT_HREF, NAV_LINKS } from "@/lib/demo-data";
import { EASE_OUT_EXPO } from "@/lib/animations";
import { cn } from "@/lib/utils";

export function Navbar() {
  const { scrollY } = useScroll();
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);

  useMotionValueEvent(scrollY, "change", (v) => setScrolled(v > 24));

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <>
      <header className="pointer-events-none fixed inset-x-0 top-0 z-50 flex justify-center px-3 pt-3 sm:px-4 sm:pt-5">
        <nav
          aria-label="Primary"
          className={cn(
            "glass edge-light pointer-events-auto relative flex w-full max-w-[1140px] items-center justify-between rounded-full pl-4 pr-2",
            "transition-[height,background-color,box-shadow,border-color] duration-300 ease-out-expo",
            scrolled
              ? "h-[50px] border-white/[0.12] bg-[rgba(8,12,18,0.84)] shadow-nav"
              : "h-[58px] shadow-[0_8px_30px_-18px_rgba(0,0,0,0.7)]",
          )}
        >
          <Logo />

          <ul className="hidden items-center gap-0.5 md:flex">
            {NAV_LINKS.map((l) => (
              <li key={l.href}>
                <a
                  href={l.href}
                  className="group relative inline-flex items-center rounded-full px-3.5 py-2 text-[13.5px] text-fg-muted transition-colors duration-200 hover:text-fg"
                >
                  {l.label}
                  <span
                    aria-hidden="true"
                    className="absolute inset-x-3.5 -bottom-px h-px origin-center scale-x-50 bg-[linear-gradient(90deg,transparent,rgba(89,217,255,0.9),transparent)] opacity-0 transition-[opacity,transform] duration-200 ease-out-expo group-hover:scale-x-100 group-hover:opacity-100"
                  />
                </a>
              </li>
            ))}
          </ul>

          <div className="hidden items-center gap-1 md:flex">
            <GlowButton variant="ghost" size="sm" href="#cta">
              Log in
            </GlowButton>
            <GlowButton size="sm" href={CONTACT_HREF} icon={<ArrowRight className="h-3.5 w-3.5" />}>
              Request access
            </GlowButton>
          </div>

          <div className="flex items-center gap-1 md:hidden">
            <GlowButton size="sm" href={CONTACT_HREF}>
              Access
            </GlowButton>
            <button
              type="button"
              aria-label={open ? "Close menu" : "Open menu"}
              aria-expanded={open}
              aria-controls="mobile-menu"
              onClick={() => setOpen((o) => !o)}
              className="grid h-10 w-10 place-items-center rounded-full text-fg-muted transition-colors hover:bg-white/[0.06] hover:text-fg"
            >
              {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </button>
          </div>
        </nav>
      </header>

      <AnimatePresence>
        {open && (
          <motion.div
            id="mobile-menu"
            key="menu"
            initial={{ opacity: 0, y: -8, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -6, scale: 0.98 }}
            transition={{ duration: 0.28, ease: EASE_OUT_EXPO }}
            className="glass-strong fixed inset-x-3 top-[74px] z-40 rounded-2xl p-2 shadow-nav md:hidden"
          >
            <ul className="flex flex-col">
              {NAV_LINKS.map((l) => (
                <li key={l.href}>
                  <a
                    href={l.href}
                    onClick={() => setOpen(false)}
                    className="flex h-12 items-center rounded-xl px-4 text-[15px] text-fg-muted transition-colors hover:bg-white/[0.05] hover:text-fg"
                  >
                    {l.label}
                  </a>
                </li>
              ))}
              <li className="mt-1 border-t border-line pt-1">
                <a
                  href="#cta"
                  onClick={() => setOpen(false)}
                  className="flex h-12 items-center rounded-xl px-4 text-[15px] text-fg-muted transition-colors hover:bg-white/[0.05] hover:text-fg"
                >
                  Log in
                </a>
              </li>
            </ul>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
