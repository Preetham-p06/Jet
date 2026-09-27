import { cn } from "@/lib/utils";

/** Abstract jet-stream trajectory: a rising sweep with fading contrail echoes. */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      className={cn("h-6 w-6 shrink-0", className)}
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="js-mark-grad" x1="3" y1="18" x2="21" y2="6" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#5B8CFF" />
          <stop offset="1" stopColor="#59D9FF" />
        </linearGradient>
      </defs>
      <path
        d="M3 18C9.5 18 11 7 21 6"
        stroke="url(#js-mark-grad)"
        strokeWidth="2.2"
        strokeLinecap="round"
      />
      <path
        d="M3 13.6C6.6 13.6 8 10.6 10.6 9.6"
        stroke="url(#js-mark-grad)"
        strokeWidth="1.6"
        strokeLinecap="round"
        opacity="0.5"
      />
      <path
        d="M3 9.2C4.7 9.2 5.7 8.1 7 7.5"
        stroke="url(#js-mark-grad)"
        strokeWidth="1.2"
        strokeLinecap="round"
        opacity="0.28"
      />
      <circle cx="21" cy="6" r="1.7" fill="#DDF8FF" />
    </svg>
  );
}

export function Logo({ className, href = "#top" }: { className?: string; href?: string }) {
  return (
    <a
      href={href}
      className={cn("inline-flex items-center gap-2.5 rounded-full", className)}
      title="Back to top"
    >
      <LogoMark />
      <span className="text-[15px] font-semibold tracking-[-0.02em] text-fg">JetStream</span>
      <span className="rounded-md border border-line px-1.5 py-px font-mono text-[10px] tracking-[0.12em] text-fg-dim">
        AI
      </span>
    </a>
  );
}
