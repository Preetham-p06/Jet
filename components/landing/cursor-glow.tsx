"use client";

import { useEffect, useState } from "react";
import { motion, useSpring, useTransform } from "motion/react";
import { usePointer } from "@/lib/pointer";
import { useReducedMotionSafe } from "@/lib/use-reduced-motion";

const PRIMARY = 680;
const TRAIL = 340;

/**
 * Two soft radial glows that follow the pointer: a fast primary and a
 * slower trailing echo. Hidden on touch devices and under reduced motion.
 */
export function CursorGlow() {
  const { x, y, active } = usePointer();
  const reduce = useReducedMotionSafe();
  const [enabled, setEnabled] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia("(hover: hover) and (pointer: fine)");
    const update = () => setEnabled(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);

  const px = useSpring(x, { stiffness: 140, damping: 24, mass: 0.5 });
  const py = useSpring(y, { stiffness: 140, damping: 24, mass: 0.5 });
  const tx = useSpring(x, { stiffness: 38, damping: 18, mass: 1.1 });
  const ty = useSpring(y, { stiffness: 38, damping: 18, mass: 1.1 });
  const opacity = useSpring(active, { stiffness: 80, damping: 20 });

  const pX = useTransform(px, (v) => v - PRIMARY / 2);
  const pY = useTransform(py, (v) => v - PRIMARY / 2);
  const tX = useTransform(tx, (v) => v - TRAIL / 2);
  const tY = useTransform(ty, (v) => v - TRAIL / 2);

  if (!enabled || reduce) return null;

  return (
    <div aria-hidden="true" className="pointer-events-none fixed inset-0 z-[1] overflow-hidden">
      <motion.div
        className="absolute left-0 top-0 rounded-full mix-blend-screen will-change-transform"
        style={{
          width: PRIMARY,
          height: PRIMARY,
          x: pX,
          y: pY,
          opacity,
          background:
            "radial-gradient(circle, rgba(91,140,255,0.16) 0%, rgba(89,217,255,0.07) 32%, rgba(89,217,255,0) 66%)",
        }}
      />
      <motion.div
        className="absolute left-0 top-0 rounded-full mix-blend-screen will-change-transform"
        style={{
          width: TRAIL,
          height: TRAIL,
          x: tX,
          y: tY,
          opacity,
          background:
            "radial-gradient(circle, rgba(89,217,255,0.13) 0%, rgba(221,248,255,0.04) 40%, rgba(89,217,255,0) 68%)",
        }}
      />
    </div>
  );
}
