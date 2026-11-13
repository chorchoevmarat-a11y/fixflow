"use client";

import { useRouter } from "next/navigation";
import { useEffect, useSyncExternalStore, type ReactNode } from "react";
import { Notice, Spinner } from "@/components/ui";
import { currentMembership, useSession, type Role } from "@/lib/session";

const noopSubscribe = () => () => {};

/** True only after hydration, so server and first client render agree. */
export function useHydrated(): boolean {
  return useSyncExternalStore(
    noopSubscribe,
    () => true,
    () => false,
  );
}

export function AuthGuard({ children, roles }: { children: ReactNode; roles?: Role[] }) {
  const router = useRouter();
  const hydrated = useHydrated();
  const session = useSession();

  useEffect(() => {
    if (hydrated && !session) router.replace("/login");
  }, [hydrated, session, router]);

  if (!hydrated || !session) return <Spinner label="Checking your session…" />;
  const membership = currentMembership(session);
  if (roles && (!membership || !roles.includes(membership.role))) {
    return (
      <Notice kind="warn">
        <strong>Not available for your role.</strong> Ask an administrator if you need access to this screen.
      </Notice>
    );
  }
  return <>{children}</>;
}
