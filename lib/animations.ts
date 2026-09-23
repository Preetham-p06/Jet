import type { Transition, Variants } from "motion/react";

/** Expo-out: fast start, long soft landing. Used for nearly every entrance. */
export const EASE_OUT_EXPO: [number, number, number, number] = [0.16, 1, 0.3, 1];
export const EASE_IN_OUT_EXPO: [number, number, number, number] = [0.87, 0, 0.13, 1];

/** Durations in seconds. */
export const DUR = {
  micro: 0.18,
  standard: 0.32,
  large: 0.7,
  hero: 1.1,
} as const;

export const springSoft: Transition = { type: "spring", stiffness: 220, damping: 28, mass: 0.9 };
export const springSnappy: Transition = { type: "spring", stiffness: 420, damping: 30 };
export const springTilt: Transition = { type: "spring", stiffness: 120, damping: 20, mass: 0.6 };

export const enter: Transition = { duration: DUR.large, ease: EASE_OUT_EXPO };
export const enterFast: Transition = { duration: DUR.standard, ease: EASE_OUT_EXPO };

/**
 * Standard reveal: rise + fade + blur-off.
 * Pass a number via the `custom` prop to delay this element.
 */
export const fadeUp: Variants = {
  hidden: { opacity: 0, y: 18, filter: "blur(6px)" },
  show: (delay: number = 0) => ({
    opacity: 1,
    y: 0,
    filter: "blur(0px)",
    transition: { ...enter, delay },
  }),
};

export const fadeIn: Variants = {
  hidden: { opacity: 0 },
  show: (delay: number = 0) => ({ opacity: 1, transition: { ...enter, delay } }),
};

export const scaleIn: Variants = {
  hidden: { opacity: 0, scale: 0.96, y: 10 },
  show: (delay: number = 0) => ({
    opacity: 1,
    scale: 1,
    y: 0,
    transition: { ...enter, delay },
  }),
};

/** Parent container that staggers its children. */
export const stagger = (staggerChildren = 0.07, delayChildren = 0.05): Variants => ({
  hidden: {},
  show: { transition: { staggerChildren, delayChildren } },
});

/** Word-by-word headline reveal. */
export const wordReveal: Variants = {
  hidden: { opacity: 0, y: "0.35em", filter: "blur(8px)" },
  show: {
    opacity: 1,
    y: 0,
    filter: "blur(0px)",
    transition: { duration: 0.9, ease: EASE_OUT_EXPO },
  },
};

/** Viewport options shared by scroll reveals. */
export const viewportOnce = { once: true, amount: 0.25 } as const;
