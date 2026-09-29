import { Building2, ChartNoAxesColumn, PlaneTakeoff, ScrollText, Settings, type LucideIcon } from "lucide-react";
import type { Capability } from "@/lib/api/types";

export type NavItem = {
  href: string;
  label: string;
  icon: LucideIcon;
  /** Hidden unless `/auth/me` grants this capability. */
  requires?: Capability;
};

export const NAV_ITEMS: NavItem[] = [
  { href: "/trips", label: "Trips", icon: PlaneTakeoff },
  { href: "/operators", label: "Operators", icon: Building2 },
  { href: "/analytics", label: "Analytics", icon: ChartNoAxesColumn, requires: "analytics.view" },
  { href: "/settings", label: "Settings", icon: Settings },
  { href: "/audit", label: "Audit", icon: ScrollText, requires: "audit.view" },
];

export function visibleNav(capabilities: readonly string[]): NavItem[] {
  return NAV_ITEMS.filter((item) => !item.requires || capabilities.includes(item.requires));
}

export function isActive(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}
