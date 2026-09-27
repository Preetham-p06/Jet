import { Logo } from "@/components/ui/logo";
import { FOOTER_LINKS } from "@/lib/demo-data";

export function Footer() {
  return (
    <footer className="relative z-10 border-t border-line">
      <div className="container-x flex flex-col gap-8 py-12 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <Logo />
          <p className="mt-3 max-w-xs text-[13px] leading-relaxed text-fg-muted">
            The AI quote intelligence layer for private aviation.
          </p>
        </div>
        <nav aria-label="Footer">
          <ul className="flex flex-wrap gap-x-7 gap-y-3 text-[13.5px]">
            {FOOTER_LINKS.map((l) => (
              <li key={l.label}>
                <a href={l.href} className="text-fg-muted transition-colors duration-200 hover:text-fg">
                  {l.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>
      </div>
      <div className="container-x flex flex-col gap-2 border-t border-line py-6 font-mono text-[11px] text-fg-dim sm:flex-row sm:items-center sm:justify-between">
        <p>© 2026 JetStream AI</p>
        <p>Demo content uses fictional operators, aircraft availability and prices.</p>
      </div>
    </footer>
  );
}
