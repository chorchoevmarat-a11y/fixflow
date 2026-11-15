"use client";

import { useSyncExternalStore } from "react";

export type Role = "REQUESTER" | "DISPATCHER" | "ADMIN" | "TECHNICIAN";

export interface Membership {
  membership_id: string;
  organization_id: string;
  organization_name: string;
  timezone: string;
  currency: string;
  role: Role;
  technician_id: string | null;
}

export interface Session {
  token: string;
  expiresAt: string;
  user: { id: string; email: string; full_name: string };
  memberships: Membership[];
  orgId: string | null;
}

const KEY = "fixflow.session";
const listeners = new Set<() => void>();
let cachedRaw: string | null | undefined;
let cachedValue: Session | null = null;

function read(): Session | null {
  if (typeof window === "undefined") return null;
  let raw: string | null = null;
  try {
    raw = window.sessionStorage.getItem(KEY);
  } catch {
    raw = null;
  }
  if (raw === cachedRaw) return cachedValue;
  cachedRaw = raw;
  try {
    cachedValue = raw ? (JSON.parse(raw) as Session) : null;
  } catch {
    cachedValue = null;
  }
  return cachedValue;
}

function write(session: Session | null): void {
  try {
    if (session) window.sessionStorage.setItem(KEY, JSON.stringify(session));
    else window.sessionStorage.removeItem(KEY);
  } catch {
    /* storage unavailable: the session then only lives for this page load */
  }
  cachedRaw = undefined;
  listeners.forEach((listener) => listener());
}

export function getSession(): Session | null {
  const session = read();
  if (session && new Date(session.expiresAt).getTime() <= Date.now()) return null;
  return session;
}

/** Sessions live in sessionStorage: per tab, gone when the tab closes. */
export function saveSession(session: Session): void {
  write(session);
}

export function clearSession(): void {
  write(null);
}

export function selectOrganization(orgId: string): void {
  const session = read();
  if (session && session.memberships.some((m) => m.organization_id === orgId)) {
    write({ ...session, orgId });
  }
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function useSession(): Session | null {
  return useSyncExternalStore(subscribe, getSession, () => null);
}

export function currentMembership(session: Session | null): Membership | null {
  if (!session?.orgId) return null;
  return session.memberships.find((m) => m.organization_id === session.orgId) ?? null;
}

export function useMembership(): Membership | null {
  return currentMembership(useSession());
}

export const isStaff = (role?: Role | null): boolean => role === "ADMIN" || role === "DISPATCHER";
