import { useId, type ReactNode } from "react";
import { cn } from "@/lib/utils";

type Props = {
  content: ReactNode;
  children: ReactNode;
  className?: string;
  triggerClassName?: string;
  side?: "top" | "bottom";
};

/**
 * CSS-driven tooltip. The trigger is a real button, so the tooltip is
 * reachable by keyboard focus and by tap on touch devices.
 */
export function Tooltip({ content, children, className, triggerClassName, side = "top" }: Props) {
  const id = useId();
  return (
    <span className={cn("group/tt relative inline-flex", className)}>
      <button
        type="button"
        aria-describedby={id}
        className={cn(
          "inline-flex items-center gap-1 rounded-md underline decoration-dotted decoration-fg-dim underline-offset-4 transition-colors duration-150 hover:decoration-cyan focus-visible:decoration-cyan",
          triggerClassName,
        )}
      >
        {children}
      </button>
      <span
        role="tooltip"
        id={id}
        className={cn(
          "glass-strong pointer-events-none absolute left-1/2 z-30 w-max max-w-[260px] -translate-x-1/2 rounded-lg px-3 py-2 text-left text-xs leading-relaxed text-fg-muted shadow-card",
          "opacity-0 transition-[opacity,transform] duration-[180ms] ease-out-expo",
          "group-hover/tt:opacity-100 group-focus-within/tt:opacity-100",
          side === "top"
            ? "bottom-[calc(100%+8px)] translate-y-1 group-hover/tt:translate-y-0 group-focus-within/tt:translate-y-0"
            : "top-[calc(100%+8px)] -translate-y-1 group-hover/tt:translate-y-0 group-focus-within/tt:translate-y-0",
        )}
      >
        {content}
      </span>
    </span>
  );
}
