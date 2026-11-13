"use client";

import { useState } from "react";
import { AuthGuard } from "@/components/auth-guard";
import { Button, Card, ConfirmButton, Empty, ErrorNote, Modal, PageHeader, Pagination, SelectField, Spinner, TextField } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useAction, useApiQuery } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import type { Page, StaffMember } from "@/lib/types";

const ROLES = ["REQUESTER", "DISPATCHER", "TECHNICIAN", "ADMIN"] as const;

function AddForm({ onDone }: { onDone: () => void }) {
  const [f, setF] = useState({ email: "", full_name: "", password: "", role: "REQUESTER" });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const create = useAction(() => api.post("/staff", { ...f, email: f.email.trim(), full_name: f.full_name.trim() }), {
    success: "Member added.",
    onSuccess: onDone,
    silentError: true,
  });
  const server = create.error instanceof ApiError ? create.error.fields : {};
  const set = (k: string, v: string) => setF((s) => ({ ...s, [k]: v }));
  return (
    <form
      className="stack"
      onSubmit={(e) => {
        e.preventDefault();
        const found: Record<string, string> = {};
        if (!/^\S+@\S+\.\S+$/.test(f.email.trim())) found.email = "Enter a valid email address.";
        if (f.full_name.trim().length < 2) found.full_name = "Name is required.";
        if (f.password.length < 10) found.password = "Password needs at least 10 characters.";
        setErrors(found);
        if (!Object.keys(found).length && !create.isPending) create.mutate(undefined);
      }}
    >
      <TextField label="Email" type="email" value={f.email} onChange={(e) => set("email", e.target.value)} error={errors.email ?? server.email} />
      <TextField label="Full name" value={f.full_name} onChange={(e) => set("full_name", e.target.value)} error={errors.full_name ?? server.full_name} />
      <TextField label="Initial password" type="password" autoComplete="new-password" value={f.password} onChange={(e) => set("password", e.target.value)} error={errors.password ?? server.password} hint="Ignored if this person already has an account in another organization." />
      <SelectField label="Role in this organization" value={f.role} onChange={(e) => set("role", e.target.value)}>
        {ROLES.map((r) => (
          <option key={r} value={r}>
            {r.toLowerCase()}
          </option>
        ))}
      </SelectField>
      {create.error && !Object.keys(server).length ? <ErrorNote error={create.error} /> : null}
      <div className="row end">
        <Button variant="secondary" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" loading={create.isPending}>
          Add member
        </Button>
      </div>
    </form>
  );
}

function View() {
  const session = useSession();
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [role, setRole] = useState("");
  const [open, setOpen] = useState(false);
  const list = useApiQuery<Page<StaffMember>>("/staff", { page, page_size: 15, q, role });
  const update = useAction((input: { id: string; body: Record<string, unknown> }) => api.patch(`/staff/${input.id}`, input.body), { success: "Member updated." });
  const myUser = session?.user.id;
  return (
    <>
      <PageHeader title="Staff & roles" actions={<Button onClick={() => setOpen(true)}>Add member</Button>} />
      <Card>
        <div className="grid cols-3">
          <TextField label="Search" type="search" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
          <SelectField label="Role" value={role} onChange={(e) => { setRole(e.target.value); setPage(1); }}>
            <option value="">All roles</option>
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {r.toLowerCase()}
              </option>
            ))}
          </SelectField>
        </div>
        {list.isLoading ? <Spinner /> : null}
        <ErrorNote error={list.error} onRetry={() => void list.refetch()} />
        {list.data?.items.length === 0 ? <Empty title="No members" /> : null}
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Email</th>
                <th>Role</th>
                <th>Status</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {list.data?.items.map((m) => {
                const self = m.user_id === myUser;
                return (
                  <tr key={m.membership_id}>
                    <td>{m.full_name}</td>
                    <td>{m.email}</td>
                    <td>
                      <select
                        aria-label={`Role of ${m.full_name}`}
                        value={m.role}
                        disabled={self || update.isPending}
                        onChange={(e) => update.mutate({ id: m.membership_id, body: { role: e.target.value } })}
                        style={{ width: "auto" }}
                      >
                        {ROLES.map((r) => (
                          <option key={r} value={r}>
                            {r.toLowerCase()}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td>{m.is_active ? "Active" : "Deactivated"}</td>
                    <td>
                      {self ? (
                        <span className="muted small">You</span>
                      ) : m.is_active ? (
                        <ConfirmButton
                          small
                          label="Deactivate"
                          title={`Deactivate ${m.full_name}?`}
                          message="They are signed out of this organization immediately. History and attribution are kept."
                          onConfirm={() => update.mutate({ id: m.membership_id, body: { is_active: false } })}
                        />
                      ) : (
                        <Button small variant="secondary" onClick={() => update.mutate({ id: m.membership_id, body: { is_active: true } })}>
                          Reactivate
                        </Button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {list.data ? <Pagination page={list.data.page} totalPages={list.data.total_pages} total={list.data.total} onChange={setPage} /> : null}
      </Card>
      <Modal title="Add member" open={open} onClose={() => setOpen(false)}>
        <AddForm onDone={() => setOpen(false)} />
      </Modal>
    </>
  );
}

export default function StaffPage() {
  return (
    <AuthGuard roles={["ADMIN"]}>
      <View />
    </AuthGuard>
  );
}
