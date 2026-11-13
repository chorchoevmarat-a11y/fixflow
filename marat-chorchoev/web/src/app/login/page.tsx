"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { Button, Notice, SelectField, TextField } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { homeFor } from "@/lib/nav";
import { saveSession, type Membership, type Session } from "@/lib/session";

interface LoginResponse {
  access_token: string;
  expires_at: string;
  user: Session["user"];
  memberships: Membership[];
}

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [choice, setChoice] = useState<{ session: Omit<Session, "orgId"> } | null>(null);
  const [orgId, setOrgId] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (pending) return;
    const errors: Record<string, string> = {};
    if (!email.trim()) errors.email = "Enter your email address.";
    if (!password) errors.password = "Enter your password.";
    setFieldErrors(errors);
    if (Object.keys(errors).length) return;
    setPending(true);
    setError(null);
    try {
      const data = await api.post<LoginResponse>("/auth/login", { email: email.trim(), password });
      const base = { token: data.access_token, expiresAt: data.expires_at, user: data.user, memberships: data.memberships };
      if (data.memberships.length === 1) {
        finish({ ...base, orgId: data.memberships[0].organization_id });
      } else {
        // AUTH-03: with several memberships the person explicitly picks one.
        setChoice({ session: base });
        setOrgId(data.memberships[0].organization_id);
      }
    } catch (e) {
      const err = e as ApiError;
      setError(err.message);
      if (err.status === 422) setFieldErrors(err.fields);
    } finally {
      setPending(false);
    }
  }

  function finish(session: Session) {
    saveSession(session);
    const membership = session.memberships.find((m) => m.organization_id === session.orgId);
    router.replace(membership ? homeFor(membership.role) : "/requests");
  }

  return (
    <main className="login-wrap">
      <div className="card login-card">
        <h1>FixFlow</h1>
        <p className="muted">Sign in to your service organization.</p>
        {choice ? (
          <form
            className="stack"
            onSubmit={(e) => {
              e.preventDefault();
              finish({ ...choice.session, orgId });
            }}
          >
            <Notice>
              You belong to several organizations. Choose the one to work in; you can switch later.
            </Notice>
            <SelectField label="Organization" value={orgId} onChange={(e) => setOrgId(e.target.value)}>
              {choice.session.memberships.map((m) => (
                <option key={m.organization_id} value={m.organization_id}>
                  {m.organization_name} — {m.role.toLowerCase()}
                </option>
              ))}
            </SelectField>
            <Button type="submit">Continue</Button>
          </form>
        ) : (
          <form className="stack" onSubmit={submit} noValidate>
            {error ? (
              <div className="notice notice-error" role="alert">
                <div>{error}</div>
              </div>
            ) : null}
            <TextField
              label="Email"
              type="email"
              autoComplete="username"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              error={fieldErrors.email}
            />
            <TextField
              label="Password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              error={fieldErrors.password}
            />
            <Button type="submit" loading={pending}>
              Sign in
            </Button>
            <p className="muted small">Demo accounts are listed in the project README.</p>
          </form>
        )}
      </div>
    </main>
  );
}
