import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const usd = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

export function formatUSD(value: number) {
  return usd.format(value);
}

export function formatSigned(value: number) {
  return `${value >= 0 ? "+" : "−"}${usd.format(Math.abs(value))}`;
}

export const clamp = (n: number, min: number, max: number) =>
  Math.min(max, Math.max(min, n));
