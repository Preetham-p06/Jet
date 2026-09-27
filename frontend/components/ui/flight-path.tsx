"use client";

import { useEffect, useRef } from "react";
import { motion, type MotionValue } from "motion/react";
import { EASE_OUT_EXPO } from "@/lib/animations";
import { useReducedMotionSafe } from "@/lib/use-reduced-motion";

/** Shared gradient + glow filter. Render once per <svg>. */
export function FlightDefs({ id = "fp" }: { id?: string }) {
  return (
    <defs>
      <linearGradient id={`${id}-grad`} x1="0" y1="0" x2="1" y2="0">
        <stop offset="0" stopColor="#5B8CFF" />
        <stop offset="0.6" stopColor="#59D9FF" />
        <stop offset="1" stopColor="#DDF8FF" />
      </linearGradient>
      <filter id={`${id}-glow`} x="-20%" y="-200%" width="140%" height="500%">
        <feGaussianBlur stdDeviation="3" result="b" />
        <feMerge>
          <feMergeNode in="b" />
          <feMergeNode in="SourceGraphic" />
        </feMerge>
      </filter>
    </defs>
  );
}

type PathProps = {
  d: string;
  /** 0–1. A MotionValue binds to scroll; a number animates in on view. */
  progress?: number | MotionValue<number>;
  defsId?: string;
  strokeWidth?: number;
  /** Faint full-length track under the lit path. */
  track?: boolean;
  glow?: boolean;
  /** Number of pulses travelling along the path. */
  dots?: number;
  dotDuration?: number;
  dotRadius?: number;
  className?: string;
  delay?: number;
};

export function FlightPath({
  d,
  progress = 1,
  defsId = "fp",
  strokeWidth = 1.5,
  track = true,
  glow = true,
  dots = 0,
  dotDuration = 6,
  dotRadius = 2.4,
  className,
  delay = 0,
}: PathProps) {
  const isMotionValue = typeof progress !== "number";
  const pathRef = useRef<SVGPathElement>(null);
  const dotsRef = useRef<SVGGElement>(null);
  const reduce = useReducedMotionSafe();

  // Pulses travelling along the path (rAF + getPointAtLength: works everywhere).
  useEffect(() => {
    const path = pathRef.current;
    const group = dotsRef.current;
    if (!path || !group || dots === 0 || reduce) return;

    const svg = path.ownerSVGElement;
    const circles = Array.from(group.querySelectorAll("circle"));
    const length = path.getTotalLength();
    let raf = 0;
    let running = false;
    let startTs = 0;

    const frame = (ts: number) => {
      if (!startTs) startTs = ts;
      const elapsed = (ts - startTs) / 1000;
      const limit = isMotionValue ? (progress as MotionValue<number>).get() : 1;
      circles.forEach((c, i) => {
        const t = ((elapsed / dotDuration) + i / dots) % 1;
        const visible = t <= limit;
        const p = path.getPointAtLength(t * length);
        c.setAttribute("cx", String(p.x));
        c.setAttribute("cy", String(p.y));
        // fade in/out at both ends of the path
        const edge = Math.min(t, 1 - t) * 8;
        c.setAttribute("opacity", visible ? String(Math.min(1, edge)) : "0");
      });
      raf = requestAnimationFrame(frame);
    };

    const start = () => {
      if (running) return;
      running = true;
      raf = requestAnimationFrame(frame);
    };
    const stop = () => {
      running = false;
      cancelAnimationFrame(raf);
    };

    const io = new IntersectionObserver(
      ([entry]) => (entry.isIntersecting && !document.hidden ? start() : stop()),
      { threshold: 0 },
    );
    if (svg) io.observe(svg);
    const onVis = () => (document.hidden ? stop() : start());
    document.addEventListener("visibilitychange", onVis);

    return () => {
      stop();
      io.disconnect();
      document.removeEventListener("visibilitychange", onVis);
    };
  }, [dots, dotDuration, reduce, isMotionValue, progress]);

  const stroke = `url(#${defsId}-grad)`;

  return (
    <g className={className}>
      {track && (
        <path d={d} fill="none" stroke="white" strokeOpacity="0.08" strokeWidth={strokeWidth} />
      )}
      {isMotionValue ? (
        <motion.path
          ref={pathRef}
          d={d}
          fill="none"
          stroke={stroke}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          style={{ pathLength: progress as MotionValue<number> }}
          filter={glow ? `url(#${defsId}-glow)` : undefined}
        />
      ) : (
        <motion.path
          ref={pathRef}
          d={d}
          fill="none"
          stroke={stroke}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          initial={{ pathLength: 0, opacity: 0.4 }}
          whileInView={{ pathLength: progress, opacity: 1 }}
          viewport={{ once: true, amount: 0.3 }}
          transition={{ duration: 1.8, ease: EASE_OUT_EXPO, delay }}
          filter={glow ? `url(#${defsId}-glow)` : undefined}
        />
      )}
      {dots > 0 && (
        <g ref={dotsRef}>
          {Array.from({ length: dots }).map((_, i) => (
            <circle
              key={i}
              r={dotRadius}
              fill="#DDF8FF"
              opacity="0"
              filter={glow ? `url(#${defsId}-glow)` : undefined}
            />
          ))}
        </g>
      )}
    </g>
  );
}
