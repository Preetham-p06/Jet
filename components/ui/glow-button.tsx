import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

type Variant = "primary" | "secondary" | "ghost";
type Size = "sm" | "md" | "lg";

type Props = {
  variant?: Variant;
  size?: Size;
  href?: string;
  icon?: ReactNode;
  iconPosition?: "left" | "right";
  className?: string;
  children: ReactNode;
  onClick?: () => void;
  type?: "button" | "submit";
  disabled?: boolean;
  "aria-label"?: string;
};

const sizes: Record<Size, string> = {
  sm: "h-9 px-4 text-[13px]",
  md: "h-11 px-5 text-sm",
  lg: "h-12 px-6 text-[15px]",
};

const variants: Record<Variant, string> = {
  primary: cn(
    "overflow-hidden text-bg-deep",
    "bg-[linear-gradient(135deg,#f2fdff_0%,#9fe9ff_38%,#5b8cff_100%)]",
    "shadow-[0_0_0_1px_rgba(221,248,255,0.25),0_8px_24px_-8px_rgba(89,217,255,0.55)]",
    "hover:shadow-[0_0_0_1px_rgba(221,248,255,0.45),0_16px_40px_-10px_rgba(89,217,255,0.8)]",
    "hover:-translate-y-0.5 active:translate-y-0 active:scale-[0.985]",
  ),
  secondary: cn(
    "glass text-fg",
    "hover:border-white/20 hover:bg-white/[0.06] hover:-translate-y-0.5 active:translate-y-0",
  ),
  ghost: "text-fg-muted hover:text-fg hover:bg-white/[0.04]",
};

export function GlowButton({
  variant = "primary",
  size = "md",
  href,
  icon,
  iconPosition = "right",
  className,
  children,
  onClick,
  type = "button",
  disabled,
  ...rest
}: Props) {
  const classes = cn(
    "group relative inline-flex select-none items-center justify-center gap-2 whitespace-nowrap rounded-full font-medium",
    "transition-[transform,box-shadow,background-color,border-color,color] duration-200 ease-out-expo",
    "disabled:pointer-events-none disabled:opacity-50",
    sizes[size],
    variants[variant],
    className,
  );

  const iconEl = icon ? (
    <span
      className={cn(
        "inline-flex transition-transform duration-200 ease-out-expo",
        iconPosition === "right" ? "group-hover:translate-x-0.5" : "group-hover:-translate-x-0.5",
      )}
      aria-hidden="true"
    >
      {icon}
    </span>
  ) : null;

  const inner = (
    <>
      {variant === "primary" && (
        <span
          aria-hidden="true"
          className="pointer-events-none absolute inset-y-0 left-0 w-1/3 bg-white/40 blur-md animate-sheen motion-reduce:animate-none"
        />
      )}
      {iconPosition === "left" && iconEl}
      <span className="relative">{children}</span>
      {iconPosition === "right" && iconEl}
    </>
  );

  if (href) {
    return (
      <a href={href} className={classes} aria-label={rest["aria-label"]}>
        {inner}
      </a>
    );
  }
  return (
    <button
      type={type}
      className={classes}
      onClick={onClick}
      disabled={disabled}
      aria-label={rest["aria-label"]}
    >
      {inner}
    </button>
  );
}
