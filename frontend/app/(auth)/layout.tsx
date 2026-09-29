import Link from "next/link";
import { AmbientBackground } from "@/components/landing/ambient-background";
import { LogoMark } from "@/components/ui/logo";

export default function AuthLayout({ children }: LayoutProps<"/">) {
  return (
    <>
      <AmbientBackground />
      <div className="relative z-10 flex min-h-dvh flex-1 flex-col">
        <header className="container-x flex h-20 items-center">
          <Link href="/" className="inline-flex items-center gap-2.5 rounded-full" title="JetStream AI home">
            <LogoMark />
            <span className="text-[15px] font-semibold tracking-[-0.02em] text-fg">JetStream</span>
            <span className="rounded-md border border-line px-1.5 py-px font-mono text-[10px] tracking-[0.12em] text-fg-dim">
              AI
            </span>
          </Link>
        </header>
        <main id="main" className="flex flex-1 items-start justify-center px-4 pb-16 pt-6 sm:items-center sm:pt-0">
          {children}
        </main>
      </div>
    </>
  );
}
