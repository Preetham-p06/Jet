"use client";

import { useEffect } from "react";
import { motionValue } from "motion/react";

/**
 * A single shared pointer store. Every pointer-reactive effect reads from
 * these MotionValues instead of installing its own listener.
 */
export const pointerX = motionValue(-9999);
export const pointerY = motionValue(-9999);
/** 1 while the pointer is over the document, 0 when it leaves. */
export const pointerActive = motionValue(0);

let subscribers = 0;
let teardown: (() => void) | null = null;

function install() {
  if (typeof window === "undefined") return () => {};

  const onMove = (e: PointerEvent) => {
    if (e.pointerType === "touch") return;
    pointerX.set(e.clientX);
    pointerY.set(e.clientY);
    if (pointerActive.get() !== 1) pointerActive.set(1);
  };
  const onLeave = () => pointerActive.set(0);
  const onVisibility = () => {
    if (document.hidden) pointerActive.set(0);
  };

  window.addEventListener("pointermove", onMove, { passive: true });
  document.documentElement.addEventListener("pointerleave", onLeave);
  document.addEventListener("visibilitychange", onVisibility);

  return () => {
    window.removeEventListener("pointermove", onMove);
    document.documentElement.removeEventListener("pointerleave", onLeave);
    document.removeEventListener("visibilitychange", onVisibility);
  };
}

export function subscribePointer() {
  subscribers += 1;
  if (subscribers === 1) teardown = install();
  return () => {
    subscribers -= 1;
    if (subscribers === 0 && teardown) {
      teardown();
      teardown = null;
    }
  };
}

export function usePointer() {
  useEffect(() => subscribePointer(), []);
  return { x: pointerX, y: pointerY, active: pointerActive };
}
