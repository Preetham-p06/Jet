import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

type Props = {
  children: ReactNode;
  className?: string;
  /** Glass (blur) vs. plain surface card. */
  glass?: boolean;
  /** Adds the gradient edge-light hairline. */
  edge?: boolean;
  as?: "div" | "article" | "section" | "li";
  id?: string;
};

export function GlassCard({ children, className, glass = false, edge = false, as = "div", id }: Props) {
  const Tag = as;
  return (
    <Tag
      id={id}
      className={cn(
        "relative rounded-2xl",
        glass ? "glass" : "surface-card",
        edge && "edge-light",
        className,
      )}
    >
      {children}
    </Tag>
  );
}
