"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { PriorityBadge, SlaBadge, StatusBadge } from "@/components/badges";
import { Card, Empty, ErrorNote, Pagination, SelectField, Spinner, TextField } from "@/components/ui";
import { fmtDateTime } from "@/lib/format";
import { useApiQuery } from "@/lib/hooks";
import { isStaff, useMembership } from "@/lib/session";
import type { Category, Page, RequestRow, Technician } from "@/lib/types";

const STATUSES = ["SUBMITTED", "TRIAGED", "SCHEDULED", "ACCEPTED", "IN_PROGRESS", "BLOCKED", "COMPLETED", "REOPENED", "CLOSED", "CANCELED"];

export interface Filters {
  q: string;
  status: string;
  priority: string;
  category_id: string;
  technician_id: string;
  sla_state: string;
  sort: string;
  open_only: boolean;
}

export function initialFilters(search: URLSearchParams | null): Filters {
  return {
    q: search?.get("q") ?? "",
    status: search?.get("status") ?? "",
    priority: search?.get("priority") ?? "",
    category_id: "",
    technician_id: "",
    sla_state: search?.get("sla_state") ?? "",
    sort: "newest",
    open_only: search?.get("open") === "1",
  };
}

function useDebounced<T>(value: T, ms = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return debounced;
}

export function RequestList({ initial }: { initial?: Partial<Filters> }) {
  const membership = useMembership();
  const staff = isStaff(membership?.role);
  const tz = membership?.timezone ?? "UTC";
  const [filters, setFilters] = useState<Filters>({ ...initialFilters(null), ...initial });
  const [page, setPage] = useState(1);
  const debouncedQ = useDebounced(filters.q);

  const categories = useApiQuery<Category[]>(staff ? "/categories" : null);
  const technicians = useApiQuery<Technician[]>(staff ? "/technicians" : null);
  const list = useApiQuery<Page<RequestRow>>("/requests", {
    q: debouncedQ,
    status: filters.status,
    priority: filters.priority,
    category_id: filters.category_id,
    technician_id: filters.technician_id,
    sla_state: filters.sla_state,
    open_only: filters.open_only || undefined,
    sort: filters.sort,
    page,
    page_size: 15,
  });

  const set = (patch: Partial<Filters>) => {
    setFilters((f) => ({ ...f, ...patch }));
    setPage(1);
  };

  return (
    <>
      <Card>
        <form className="grid cols-4" role="search" onSubmit={(e) => e.preventDefault()}>
          <TextField
            label="Search"
            type="search"
            placeholder="ID, title, or address"
            value={filters.q}
            onChange={(e) => set({ q: e.target.value })}
          />
          <SelectField label="Status" value={filters.status} onChange={(e) => set({ status: e.target.value })}>
            <option value="">Any status</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s.replace("_", " ").toLowerCase()}
              </option>
            ))}
          </SelectField>
          <SelectField label="Priority" value={filters.priority} onChange={(e) => set({ priority: e.target.value })}>
            <option value="">Any priority</option>
            <option value="HIGH">High</option>
            <option value="NORMAL">Normal</option>
            <option value="LOW">Low</option>
          </SelectField>
          <SelectField label="Sort" value={filters.sort} onChange={(e) => set({ sort: e.target.value })}>
            <option value="newest">Newest first</option>
            <option value="oldest">Oldest first</option>
            <option value="priority">Priority</option>
            <option value="due">Due time</option>
          </SelectField>
          {staff ? (
            <>
              <SelectField label="Category" value={filters.category_id} onChange={(e) => set({ category_id: e.target.value })}>
                <option value="">Any category</option>
                {categories.data?.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </SelectField>
              <SelectField label="Technician" value={filters.technician_id} onChange={(e) => set({ technician_id: e.target.value })}>
                <option value="">Any technician</option>
                {technicians.data?.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.full_name}
                  </option>
                ))}
              </SelectField>
              <SelectField label="SLA" value={filters.sla_state} onChange={(e) => set({ sla_state: e.target.value })}>
                <option value="">Any SLA state</option>
                <option value="ON_TRACK">On track</option>
                <option value="AT_RISK">At risk</option>
                <option value="OVERDUE">Overdue</option>
              </SelectField>
              <div className="field">
                <span className="sr-only">Open only</span>
                <label className="check" style={{ marginTop: "1.6rem" }}>
                  <input type="checkbox" checked={filters.open_only} onChange={(e) => set({ open_only: e.target.checked })} />
                  Open requests only
                </label>
              </div>
            </>
          ) : null}
        </form>
      </Card>

      <div style={{ marginTop: "1rem" }} aria-live="polite">
        {list.isLoading ? <Spinner /> : null}
        <ErrorNote error={list.error} onRetry={() => void list.refetch()} />
        {list.data && list.data.items.length === 0 ? (
          <Empty title="No requests match">Change the filters or search, or create a new request.</Empty>
        ) : null}
        {list.data && list.data.items.length > 0 ? (
          <>
            <div className="table-wrap collapse">
              <table>
                <thead>
                  <tr>
                    <th>Request</th>
                    <th>Status</th>
                    <th>Priority</th>
                    <th>Property</th>
                    {staff ? <th>Technician</th> : null}
                    <th>SLA</th>
                    <th>Created</th>
                  </tr>
                </thead>
                <tbody>
                  {list.data.items.map((r) => (
                    <tr key={r.id} className="row-link">
                      <td>
                        <Link href={`/requests/${r.id}`}>
                          <strong>{r.reference}</strong> {r.title}
                        </Link>
                        <div className="muted small">{r.category.name}</div>
                      </td>
                      <td>
                        <StatusBadge status={r.status} />
                      </td>
                      <td>
                        <PriorityBadge priority={r.priority} />
                      </td>
                      <td>
                        {r.property.name}
                        <div className="muted small">{r.property.address}</div>
                      </td>
                      {staff ? <td>{r.assignment?.is_active ? r.assignment.technician_name : "—"}</td> : null}
                      <td>
                        <SlaBadge sla={r.sla} timeZone={tz} detailed />
                      </td>
                      <td>{fmtDateTime(r.created_at, tz)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="cards-mobile">
              {list.data.items.map((r) => (
                <div className="mobile-item" key={r.id}>
                  <Link href={`/requests/${r.id}`}>
                    <strong>{r.reference}</strong> {r.title}
                  </Link>
                  <div className="row" style={{ marginTop: "0.35rem" }}>
                    <StatusBadge status={r.status} />
                    <PriorityBadge priority={r.priority} />
                    <SlaBadge sla={r.sla} timeZone={tz} />
                  </div>
                  <div className="muted small">{r.property.name}</div>
                </div>
              ))}
            </div>
            <Pagination page={list.data.page} totalPages={list.data.total_pages} total={list.data.total} onChange={setPage} />
          </>
        ) : null}
      </div>
    </>
  );
}
