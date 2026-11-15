"use client";

import Link from "next/link";
import { useState } from "react";
import { AuthGuard } from "@/components/auth-guard";
import { SlaBadge, StatusBadge } from "@/components/badges";
import { DailyChart, DistributionChart, type DailyPoint } from "@/components/charts";
import { Card, Empty, ErrorNote, PageHeader, SelectField, Spinner, TextField } from "@/components/ui";
import { fmtDateTime, fmtMoney, minutesToText, statusLabel, titleCase } from "@/lib/format";
import { useApiQuery } from "@/lib/hooks";
import { useMembership } from "@/lib/session";
import type { Category, Page, RequestRow, Technician } from "@/lib/types";

interface Dashboard {
  range: { date_from: string; date_to: string; timezone: string };
  status_counts: Record<string, number>;
  open_count: number;
  overdue_count: number;
  at_risk_count: number;
  created_in_range: number;
  completed_in_range: number;
  upcoming_appointments: {
    window_days: number;
    count: number;
    next: { request_id: string; reference: string; title: string; technician_name: string; start_at: string; end_at: string }[];
  };
  daily: { date_from: string; date_to: string; unit: string; series: DailyPoint[] };
  priority_distribution: { priority: string; count: number }[];
  category_distribution: { category: string; count: number }[];
  utilization: {
    planned_minutes: number;
    available_minutes: number;
    utilization_percent: number | null;
    technicians: { technician_id: string; full_name: string; planned_minutes: number; available_minutes: number; utilization_percent: number | null }[];
  };
  financials: {
    currency: string;
    approved_estimates_total_minor: number;
    approved_estimates_count: number;
    material_usage_total_minor: number;
    material_usage_count: number;
    note: string;
  };
}

const STATUS_ORDER = ["SUBMITTED", "TRIAGED", "SCHEDULED", "ACCEPTED", "IN_PROGRESS", "BLOCKED", "COMPLETED", "REOPENED", "CLOSED", "CANCELED"];

function DashboardView() {
  const membership = useMembership();
  const tz = membership?.timezone ?? "UTC";
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [category, setCategory] = useState("");
  const [technician, setTechnician] = useState("");

  const dashboard = useApiQuery<Dashboard>("/reports/dashboard", {
    date_from: from,
    date_to: to,
    category_id: category,
    technician_id: technician,
  });
  const categories = useApiQuery<Category[]>("/categories");
  const technicians = useApiQuery<Technician[]>("/technicians");
  const overdue = useApiQuery<Page<RequestRow>>("/requests", {
    sla_state: "OVERDUE",
    open_only: true,
    sort: "due",
    page_size: 8,
  });

  const d = dashboard.data;
  return (
    <>
      <PageHeader title="Operations dashboard" subtitle={membership ? `${membership.organization_name} · times in ${tz}` : undefined} />
      <Card className="filters">
        <div className="grid cols-4">
          <TextField label="From" type="date" value={from} onChange={(e) => setFrom(e.target.value)} hint="Default: 14 days" />
          <TextField label="To" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
          <SelectField label="Category" value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="">All categories</option>
            {categories.data?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </SelectField>
          <SelectField label="Technician" value={technician} onChange={(e) => setTechnician(e.target.value)}>
            <option value="">All technicians</option>
            {technicians.data?.map((t) => (
              <option key={t.id} value={t.id}>
                {t.full_name}
              </option>
            ))}
          </SelectField>
        </div>
      </Card>

      {dashboard.isLoading ? <Spinner /> : null}
      <ErrorNote error={dashboard.error} onRetry={() => void dashboard.refetch()} />
      {d ? (
        <div className="stack" style={{ marginTop: "1rem" }}>
          <div className="grid cols-4">
            <Card>
              <Link className="stat-link" href="/requests?open=1">
                <div className="stat">{d.open_count}</div>
                <div className="muted">Open requests</div>
              </Link>
            </Card>
            <Card>
              <Link className="stat-link" href="/requests?sla_state=OVERDUE">
                <div className="stat" style={{ color: d.overdue_count ? "var(--danger)" : undefined }}>
                  {d.overdue_count}
                </div>
                <div className="muted">Overdue ({d.at_risk_count} at risk)</div>
              </Link>
            </Card>
            <Card>
              <div className="stat">{d.upcoming_appointments.count}</div>
              <div className="muted">Appointments, next {d.upcoming_appointments.window_days} days</div>
            </Card>
            <Card>
              <div className="stat">{d.completed_in_range}</div>
              <div className="muted">
                Completed {d.range.date_from} → {d.range.date_to}
              </div>
            </Card>
          </div>

          <Card title="Reports by status (all time)">
            <div className="row">
              {STATUS_ORDER.map((s) => (
                <Link key={s} href={`/requests?status=${s}`} className="badge" style={{ textDecoration: "none", color: "inherit" }}>
                  {statusLabel(s)} <strong>{d.status_counts[s] ?? 0}</strong>
                </Link>
              ))}
            </div>
          </Card>

          <div className="grid cols-2">
            <Card title="New vs completed, last 14 days">
              <DailyChart series={d.daily.series} unit={d.daily.unit} range={`${d.daily.date_from} to ${d.daily.date_to}`} />
            </Card>
            <Card title="Priority distribution">
              <DistributionChart title="Priority distribution" rows={d.priority_distribution.map((p) => ({ label: titleCase(p.priority), count: p.count }))} />
              <h3 style={{ marginTop: "1rem" }}>By category</h3>
              <DistributionChart title="Category distribution" rows={d.category_distribution.map((c) => ({ label: c.category, count: c.count }))} />
            </Card>
          </div>

          <div className="grid cols-2">
            <Card title="Overdue queue" actions={<Link href="/requests?sla_state=OVERDUE">View all</Link>}>
              {overdue.isLoading ? <Spinner /> : null}
              {overdue.data && overdue.data.items.length === 0 ? <Empty title="Nothing is overdue" /> : null}
              {overdue.data?.items.map((r) => (
                <div key={r.id} className="row between" style={{ padding: "0.35rem 0", borderBottom: "1px solid var(--border)" }}>
                  <Link href={`/requests/${r.id}`}>
                    {r.reference} · {r.title}
                  </Link>
                  <span className="row">
                    <StatusBadge status={r.status} />
                    <SlaBadge sla={r.sla} timeZone={tz} detailed />
                  </span>
                </div>
              ))}
            </Card>
            <Card title={`Upcoming appointments (${d.upcoming_appointments.window_days} days)`}>
              {d.upcoming_appointments.next.length === 0 ? <Empty title="No upcoming appointments" /> : null}
              {d.upcoming_appointments.next.map((a) => (
                <div key={a.request_id} style={{ padding: "0.35rem 0", borderBottom: "1px solid var(--border)" }}>
                  <Link href={`/requests/${a.request_id}`}>
                    {a.reference} · {a.title}
                  </Link>
                  <div className="muted small">
                    {fmtDateTime(a.start_at, tz)} · {a.technician_name}
                  </div>
                </div>
              ))}
            </Card>
          </div>

          <div className="grid cols-2">
            <Card title="Technician utilization">
              <p className="stat">{d.utilization.utilization_percent === null ? "—" : `${d.utilization.utilization_percent}%`}</p>
              <p className="muted small">
                Planned assignment minutes ({minutesToText(d.utilization.planned_minutes)}) ÷ available working minutes (
                {minutesToText(d.utilization.available_minutes)}) for active technicians in the range, using availability
                minus time off in {d.range.timezone}. Not capped: appointments cannot overlap or exceed availability.
              </p>
              {d.utilization.technicians.map((t) => (
                <div className="hbar" key={t.technician_id}>
                  <span>{t.full_name}</span>
                  <div className="hbar-track">
                    <div className="hbar-fill" style={{ width: `${Math.min(t.utilization_percent ?? 0, 100)}%` }} />
                  </div>
                  <strong>{t.utilization_percent === null ? "—" : `${t.utilization_percent}%`}</strong>
                </div>
              ))}
            </Card>
            <Card title="Estimated values and material costs">
              <dl className="kv">
                <dt>Approved estimates</dt>
                <dd>
                  {fmtMoney(d.financials.approved_estimates_total_minor, d.financials.currency)} ({d.financials.approved_estimates_count})
                </dd>
                <dt>Material usage cost</dt>
                <dd>
                  {fmtMoney(d.financials.material_usage_total_minor, d.financials.currency)} ({d.financials.material_usage_count} entries)
                </dd>
              </dl>
              <p className="muted small">{d.financials.note} Material costs use the unit price at consumption time.</p>
            </Card>
          </div>
        </div>
      ) : null}
    </>
  );
}

export default function DashboardPage() {
  return (
    <AuthGuard roles={["ADMIN", "DISPATCHER"]}>
      <DashboardView />
    </AuthGuard>
  );
}

