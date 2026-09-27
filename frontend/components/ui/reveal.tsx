"use client";

import type { ReactNode } from "react";
import { motion } from "motion/react";
import { fadeUp, stagger } from "@/lib/animations";
import { cn } from "@/lib/utils";

type RevealProps = {
  children: ReactNode;
  className?: string;
  /** Seconds. */
  delay?: number;
  amount?: number;
  once?: boolean;
  as?: "div" | "section" | "li" | "span" | "p";
};

/** Single element: rises, fades and un-blurs when it enters the viewport. */
export function Reveal({ children, className, delay = 0, amount = 0.25, once = true, as = "div" }: RevealProps) {
  const Comp = motion[as];
  return (
    <Comp
      variants={fadeUp}
      custom={delay}
      initial="hidden"
      whileInView="show"
      viewport={{ once, amount }}
      className={className}
    >
      {children}
    </Comp>
  );
}

type GroupProps = {
  children: ReactNode;
  className?: string;
  staggerChildren?: number;
  delayChildren?: number;
  amount?: number;
  once?: boolean;
  as?: "div" | "ul" | "ol" | "section";
};

/** Container that staggers `RevealItem` children. */
export function RevealGroup({
  children,
  className,
  staggerChildren = 0.07,
  delayChildren = 0.05,
  amount = 0.2,
  once = true,
  as = "div",
}: GroupProps) {
  const Comp = motion[as];
  return (
    <Comp
      variants={stagger(staggerChildren, delayChildren)}
      initial="hidden"
      whileInView="show"
      viewport={{ once, amount }}
      className={className}
    >
      {children}
    </Comp>
  );
}

export function RevealItem({
  children,
  className,
  as = "div",
}: {
  children: ReactNode;
  className?: string;
  as?: "div" | "li" | "span" | "article";
}) {
  const Comp = motion[as];
  return (
    <Comp variants={fadeUp} className={cn(className)}>
      {children}
    </Comp>
  );
}
