"use client";

import { useId, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Plus } from "lucide-react";
import { SectionHeader } from "@/components/ui/section-header";
import { RevealGroup, RevealItem } from "@/components/ui/reveal";
import { FAQ } from "@/lib/demo-data";
import { EASE_OUT_EXPO } from "@/lib/animations";
import { cn } from "@/lib/utils";

function Item({ q, a, defaultOpen = false }: { q: string; a: string; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  const id = useId();
  return (
    <div className={cn("border-b border-line transition-colors", open && "bg-white/[0.015]")}>
      <h3>
        <button
          type="button"
          aria-expanded={open}
          aria-controls={`${id}-panel`}
          id={`${id}-button`}
          onClick={() => setOpen((o) => !o)}
          className="flex w-full items-center justify-between gap-6 px-2 py-5 text-left text-[15.5px] font-medium text-fg transition-colors hover:text-ice sm:px-3"
        >
          {q}
          <span
            aria-hidden="true"
            className={cn(
              "grid h-7 w-7 shrink-0 place-items-center rounded-full border border-line text-fg-muted transition-[transform,border-color,color] duration-300 ease-out-expo",
              open && "rotate-45 border-cyan/40 text-cyan",
            )}
          >
            <Plus className="h-3.5 w-3.5" />
          </span>
        </button>
      </h3>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            id={`${id}-panel`}
            role="region"
            aria-labelledby={`${id}-button`}
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.32, ease: EASE_OUT_EXPO }}
            className="overflow-hidden"
          >
            <p className="max-w-2xl px-2 pb-6 text-[14px] leading-relaxed text-fg-muted sm:px-3">{a}</p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export function Faq() {
  return (
    <section id="faq" className="container-x py-24 sm:py-32">
      <div className="grid gap-10 lg:grid-cols-[minmax(0,4fr)_minmax(0,8fr)] lg:gap-16">
        <div className="lg:sticky lg:top-32 lg:self-start">
          <SectionHeader eyebrow="FAQ" title="Questions brokers ask first." lead="Short answers. Longer ones on a call." />
        </div>
        <RevealGroup className="border-t border-line" staggerChildren={0.05}>
          {FAQ.map((f, i) => (
            <RevealItem key={f.q}>
              <Item q={f.q} a={f.a} defaultOpen={i === 0} />
            </RevealItem>
          ))}
        </RevealGroup>
      </div>
    </section>
  );
}
