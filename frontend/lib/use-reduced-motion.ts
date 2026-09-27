"use client";

import { useEffect, useState } from "react";

/**
 * SSR-safe `prefers-reduced-motion`.
 * Returns `false` on the server and on the first client render (so markup
 * hydrates cleanly), then resolves to the real preference in an effect.
 */
export function useReducedMotionSafe() {
  const [reduce, setReduce] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduce(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);
  return reduce;
}
