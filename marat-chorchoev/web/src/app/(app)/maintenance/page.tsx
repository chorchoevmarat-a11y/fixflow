"use client";

import Link from "next/link";
import { useState } from "react";
import { AuthGuard } from "@/components/auth-guard";
import { Button, Card, Empty, ErrorNote, Modal, Notice, PageHeader, Pagination, SelectField, Spinner, TextArea, TextField } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { localDate } from "@/lib/format";
import { useAction, useApiQuery } from "@/lib/hooks";
import { useMembership } from "@/lib/session";
import type { AssetItem, Category, Page } from "@/lib/types";

interface Plan {
  id: string;
  title: string;
  description: string;
  priority: string;
  first_date: string;
  recurrence: "WEEKLY" | "MONTHLY";
  is_enabled: boolean;
  asset: { id: string; code: string; name: string; status: string };
  category: { id: string; name: string };
  next_occurrence: string | null;
  generated_count: number;
}
interface PlanDetail extends Plan {
  generated: { request_id: string; reference: string; occurrence_date: string; status: string }[];
}

function PlanForm({ onDone }: { onDone: () => void }) {
  const tz = useMembership()?.timezone ?? "UTC";
  const assets = useApiQuery<Page<AssetItem>>("/assets", { status: "ACTIVE", page_size: 100 });
  const categories = useApiQuery<Category[]>("/categories", { enabled_only: true });
  const [f, setF] = useState({ asset_id: "", category_id: "", title: "", description: "", priority: "NORMAL", first_date: localDate(new Date(), tz), recurrence: "MONTHLY" });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const set = (k: string, v: string) => setF((s) => ({ ...s, [k]: v }));
  const create = useAction(() => api.post("/maintenance-plans", { ...f, title: f.title.trim(), description: f.description.trim() }), {
    success: "Plan created.",
    onSuccess: onDone,
    silentError: true,
  });
  const server = create.error instanceof ApiError ? create.error.fields : {};
  return (
    <form
      className="stack"
      onSubmit={(e) => {
        e.preventDefault();
        const found: Record<string, string> = {};
        if (!f.asset_id) found.asset_id = "Choose an asset.";
        if (!f.category_id) found.category_id = "Choose a category.";
        if (f.title.trim().length < 5) found.title = "Title needs 5+ characters.";
        if (f.description.trim().length < 20) found.description = "Describe the work in 20+ characters.";
        setErrors(found);
        if (!Object.keys(found).length && !create.isPending) create.mutate(undefined);
      }}
    >
      <SelectField label="Active asset" value={f.asset_id} onChange={(e) => set("asset_id", e.target.value)} error={errors.asset_id ?? server.asset_id}>
        <option value="">Choose…</option>
        {assets.data?.items.map((a) => (
          <option key={a.id} value={a.id}>
            {a.code} — {a.name}
          </option>
        ))}
      </SelectField>
      <SelectField label="Category" value={f.category_id} onChange={(e) => set("category_id", e.target.value)} error={errors.category_id ?? server.category_id}>
        <option value="">Choose…</option>
        {categories.data?.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </SelectField>
      <TextField label="Title" value={f.title} onChange={(e) => set("title", e.target.value)} error={errors.title ?? server.title} />
      <TextArea label="Description" value={f.description} onChange={(e) => set("description", e.target.value)} error={errors.description ?? server.description} rows={3} />
      <div className="grid cols-3">
        <SelectField label="Priority" value={f.priority} onChange={(e) => set("priority", e.target.value)}>
          <option value="LOW">Low</option>
          <option value="NORMAL">Normal</option>
          <option value="HIGH">High</option>
        </SelectField>
        <SelectField label="Repeats" value={f.recurrence} onChange={(e) => set("recurrence", e.target.value)}>
          <option value="WEEKLY">Weekly</option>
          <option value="MONTHLY">Monthly</option>
        </SelectField>
        <TextField label="First date" type="date" value={f.first_date} onChange={(e) => set("first_date", e.target.value)} />
      </div>
      {create.error && !Object.keys(server).length ? <ErrorNote error={create.error} /> : null}
      <div className="row end">
        <Button variant="secondary" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" loading={create.isPending}>
          Create plan
        </Button>
      </div>
    </form>
  );
}

function PlanHistory({ id }: { id: string }) {
  const detail = useApiQuery<PlanDetail>(`/maintenance-plans/${id}`);
  if (detail.isLoading) return <Spinner />;
  return (
    <ul style={{ margin: 0, paddingLeft: "1.2rem" }}>
      {detail.data?.generated.length === 0 ? <li className="muted">No requests generated yet.</li> : null}
      {detail.data?.generated.map((g) => (
        <li key={g.request_id}>
          {g.occurrence_date}: <Link href={`/requests/${g.request_id}`}>{g.reference}</Link> ({g.status.replace("_", " ").toLowerCase()})
        </li>
      ))}
    </ul>
  );
}

function MaintenanceView() {
  const tz = useMembership()?.timezone ?? "UTC";
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [asOf, setAsOf] = useState(localDate(new Date(), tz));
  const [result, setResult] = useState<string | null>(null);
  const plans = useApiQuery<Page<Plan>>("/maintenance-plans", { page, page_size: 10 });
  const toggle = useAction((p: Plan) => api.patch(`/maintenance-plans/${p.id}`, { is_enabled: !p.is_enabled }), { success: "Plan updated." });
  const generate = useAction(() => api.post<{ generated_count: number }>("/maintenance-plans/generate", { as_of: asOf }), {
    onSuccess: (r) => setResult(`${r.generated_count} request(s) generated up to ${asOf}.`),
  });
  return (
    <>
      <PageHeader title="Preventive maintenance" actions={<Button onClick={() => setOpen(true)}>New plan</Button>} />
      <Card title="Generate due requests">
        <div className="row">
          <TextField label="As of date" type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} />
          <Button loading={generate.isPending} onClick={() => generate.mutate(undefined)} style={{ alignSelf: "end" }}>
            Generate
          </Button>
        </div>
        <p className="muted small">Safe to repeat: each plan/date pair creates at most one request, even with simultaneous runs. The same job is also available as <code>python -m app.cli generate-maintenance</code>.</p>
        {result ? <Notice kind="success">{result}</Notice> : null}
      </Card>
      <div style={{ marginTop: "1rem" }}>
        {plans.isLoading ? <Spinner /> : null}
        <ErrorNote error={plans.error} onRetry={() => void plans.refetch()} />
        {plans.data?.items.length === 0 ? <Empty title="No plans yet" /> : null}
        {plans.data?.items.map((p) => (
          <Card key={p.id} title={p.title} actions={<span className="badge">{p.is_enabled ? "Enabled" : "Disabled"}</span>}>
            <p className="muted">
              {p.asset.code} · {p.asset.name} ({p.asset.status.replace("_", " ").toLowerCase()}) · {p.category.name} · {p.recurrence.toLowerCase()} from {p.first_date} · {p.priority.toLowerCase()}
            </p>
            <p>
              <strong>Next occurrence:</strong> {p.next_occurrence ?? "none (disabled or asset not active)"} · {p.generated_count} generated
            </p>
            <div className="row">
              <Button small variant="secondary" loading={toggle.isPending} onClick={() => toggle.mutate(p)}>
                {p.is_enabled ? "Disable" : "Enable"}
              </Button>
              <Button small variant="ghost" onClick={() => setExpanded(expanded === p.id ? null : p.id)}>
                {expanded === p.id ? "Hide history" : "Generated history"}
              </Button>
            </div>
            {expanded === p.id ? <PlanHistory id={p.id} /> : null}
          </Card>
        ))}
        {plans.data ? <Pagination page={plans.data.page} totalPages={plans.data.total_pages} total={plans.data.total} onChange={setPage} /> : null}
      </div>
      <Modal title="New maintenance plan" open={open} onClose={() => setOpen(false)}>
        <PlanForm onDone={() => setOpen(false)} />
      </Modal>
    </>
  );
}

export default function MaintenancePage() {
  return (
    <AuthGuard roles={["ADMIN", "DISPATCHER"]}>
      <MaintenanceView />
    </AuthGuard>
  );
}
