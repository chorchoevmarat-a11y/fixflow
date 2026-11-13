import type { Role } from "./session";

export interface NavItem {
  href: string;
  label: string;
  roles: Role[];
  group?: string;
}

const STAFF: Role[] = ["ADMIN", "DISPATCHER"];

export const NAV: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", roles: STAFF, group: "Operations" },
  { href: "/requests", label: "Requests", roles: ["REQUESTER", "DISPATCHER", "ADMIN", "TECHNICIAN"] },
  { href: "/requests/new", label: "New request", roles: ["REQUESTER", "DISPATCHER", "ADMIN"] },
  { href: "/schedule", label: "Schedule", roles: [...STAFF, "TECHNICIAN"] },
  { href: "/properties", label: "Properties & assets", roles: STAFF },
  { href: "/maintenance", label: "Maintenance plans", roles: STAFF },
  { href: "/inventory", label: "Inventory", roles: [...STAFF, "TECHNICIAN"] },
  { href: "/notifications", label: "Notifications", roles: ["REQUESTER", "DISPATCHER", "ADMIN", "TECHNICIAN"] },
  { href: "/admin/organization", label: "Organization", roles: ["ADMIN"], group: "Administration" },
  { href: "/admin/staff", label: "Staff & roles", roles: ["ADMIN"] },
  { href: "/admin/technicians", label: "Technicians", roles: ["ADMIN"] },
  { href: "/admin/categories", label: "Categories & skills", roles: ["ADMIN"] },
  { href: "/admin/audit", label: "Audit history", roles: ["ADMIN"] },
];

export function homeFor(role: Role): string {
  return role === "ADMIN" || role === "DISPATCHER" ? "/dashboard" : "/requests";
}
