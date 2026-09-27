import type { ReactNode } from "react";
import { Reveal } from "@/components/ui/reveal";
import { cn } from "@/lib/utils";

type Props = {
  eyebrow?: string;
  title: ReactNode;
  lead?: ReactNode;
  align?: "left" | "center";
  className?: string;
  size?: "md" | "lg";
};

export function SectionHeader({ eyebrow, title, lead, align = "left", className, size = "md" }: Props) {
  return (
    <Reveal
      className={cn(
        "flex flex-col",
        align === "center" && "items-center text-center",
        className,
      )}
    >
      {eyebrow && (
        <span className="eyebrow inline-flex items-center gap-2.5">
          <span className="h-px w-5 bg-cyan/70" aria-hidden="true" />
          {eyebrow}
        </span>
      )}
      <h2
        className={cn(
          "mt-4 font-semibold leading-[1.04] text-fg",
          size === "lg"
            ? "text-[2.25rem] sm:text-[3rem] lg:text-[3.6rem]"
            : "text-[2rem] sm:text-[2.5rem] lg:text-[3rem]",
        )}
      >
        {title}
      </h2>
      {lead && (
        <p
          className={cn(
            "mt-5 max-w-2xl text-base leading-relaxed text-fg-muted sm:text-lg",
            align === "center" && "mx-auto",
          )}
        >
          {lead}
        </p>
      )}
    </Reveal>
  );
}
