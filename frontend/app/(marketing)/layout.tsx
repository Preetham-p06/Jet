import { AmbientBackground } from "@/components/landing/ambient-background";
import { CursorGlow } from "@/components/landing/cursor-glow";

/** Marketing chrome: the fixed atmospheric layer and the pointer glow. */
export default function MarketingLayout({ children }: LayoutProps<"/">) {
  return (
    <>
      <AmbientBackground />
      <CursorGlow />
      {children}
    </>
  );
}
