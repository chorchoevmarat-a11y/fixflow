"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { AuthGuard } from "@/components/auth-guard";
import { Button } from "@/components/ui";
import { api } from "@/lib/api";
import { useApiQuery } from "@/lib/hooks";
import { useLiveUpdates } from "@/lib/live";
import { homeFor, NAV } from "@/lib/nav";
import { clearSession, selectOrganization, useMembership, useSession } from "@/lib/session";

function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const session = useSession();
  const membership = useMembership();
  const [open, setOpen] = useState(false);
  const hadSession = useRef(false);
  useLiveUpdates();

  useEffect(() => {
    if (session) hadSession.current = true;
    else if (hadSession.current) router.replace("/login?expired=1");
  }, [session, router]);

  const unread = useApiQuery<{ unread_count: number }>("/notifications/unread-count");

  if (!session || !membership) return null;
  const items = NAV.filter((item) => item.roles.includes(membership.role));
  const isActive = (href: string) =>
    pathname === href || (href !== "/requests" && href !== "/dashboard" && pathname.startsWith(`${href}/`));

  async function signOut() {
    try {
      await api.post("/auth/logout");
    } catch {
      /* the session may already be gone */
    }
    clearSession();
    router.replace("/login");
  }

  function switchOrg(orgId: string) {
    selectOrganization(orgId);
    const next = session?.memberships.find((m) => m.organization_id === orgId);
    router.replace(next ? homeFor(next.role) : "/requests");
  }

  return (
    <div className="shell">
      <a className="skip-link" href="#content">
        Skip to content
      </a>
      <aside className={`sidebar${open ? " open" : ""}`}>
        <div className="row between">
          <span className="brand">FixFlow</span>
          <Button className="menu-toggle" variant="secondary" small aria-expanded={open} onClick={() => setOpen(!open)}>
            Menu
          </Button>
        </div>
        <nav className="nav" aria-label="Main">
          {items.map((item) => {
            const heading = item.group ?? null; // only the first item of a group carries its name
            return (
              <span key={item.href} style={{ display: "contents" }}>
                {heading ? <span className="nav-heading">{heading}</span> : null}
                <Link
                  href={item.href}
                  aria-current={isActive(item.href) ? "page" : undefined}
                  onClick={() => setOpen(false)}
                >
                  {item.label}
                  {item.href === "/notifications" && unread.data?.unread_count ? (
                    <span className="bell-count" aria-label={`${unread.data.unread_count} unread`}>
                      {unread.data.unread_count}
                    </span>
                  ) : null}
                </Link>
              </span>
            );
          })}
        </nav>
        <div className="side-extra stack">
          {session.memberships.length > 1 ? (
            <div className="field">
              <label htmlFor="org-switch">Organization</label>
              <select id="org-switch" value={session.orgId ?? ""} onChange={(e) => switchOrg(e.target.value)}>
                {session.memberships.map((m) => (
                  <option key={m.organization_id} value={m.organization_id}>
                    {m.organization_name} ({m.role.toLowerCase()})
                  </option>
                ))}
              </select>
            </div>
          ) : (
            <p className="muted small">{membership.organization_name}</p>
          )}
          <p className="small">
            <strong>{session.user.full_name}</strong>
            <br />
            <span className="muted">{membership.role.toLowerCase()}</span>
          </p>
          <Button variant="secondary" small onClick={signOut}>
            Sign out
          </Button>
        </div>
      </aside>
      <main className="main" id="content" tabIndex={-1}>
        {children}
      </main>
    </div>
  );
}

export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <AuthGuard>
      <Shell>{children}</Shell>
    </AuthGuard>
  );
}
