"use client";

import Link from "next/link";
import { use } from "react";
import { PriorityBadge, SlaBadge, StatusBadge } from "@/components/badges";
import { DispatchPanel } from "@/components/dispatch-panel";
import { EstimatePanel } from "@/components/estimate-panel";
import { ReclassifyCard, RequestActions } from "@/components/request-actions";
import { EvidenceCard, FeedbackCard, MaterialsCard, NotesCard, Timeline } from "@/components/request-sections";
import { Card, ErrorNote, Notice, PageHeader, Spinner } from "@/components/ui";
import { fmtDateTime, fmtDuration } from "@/lib/format";
import { useApiQuery } from "@/lib/hooks";
import { isStaff, useMembership } from "@/lib/session";
import type { RequestDetail } from "@/lib/types";

export default function RequestDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const membership = useMembership();
  const tz = membership?.timezone ?? "UTC";
  const query = useApiQuery<RequestDetail>(`/requests/${id}`);
  const r = query.data;

  if (query.isLoading) return <Spinner />;
  if (query.error) {
    return (
      <>
        <ErrorNote error={query.error} onRetry={() => void query.refetch()} />
        <Link href="/requests">Back to requests</Link>
      </>
    );
  }
  if (!r) return null;
  const staff = isStaff(membership?.role);
  const appointment = r.assignment?.is_active ? r.assignment : null;

  return (
    <>
      <PageHeader
        title={`${r.reference} · ${r.title}`}
        subtitle={
          <span className="row">
            <StatusBadge status={r.status} />
            <PriorityBadge priority={r.priority} />
            <SlaBadge sla={r.sla} timeZone={tz} detailed />
            {r.is_preventive ? <span className="badge">Preventive maintenance</span> : null}
          </span>
        }
        actions={
          <Link className="btn btn-secondary" href="/requests">
            All requests
          </Link>
        }
      />
      {r.status === "REOPENED" ? <Notice kind="warn">The requester asked for rework. A dispatcher must accept it for dispatch again.</Notice> : null}
      {r.sla.state === "OVERDUE" && !r.sla.stopped_at ? <Notice kind="warn">This request is past its SLA due time.</Notice> : null}
      <div className="split">
        <div className="stack">
          <Card title="Details">
            <p style={{ whiteSpace: "pre-wrap" }}>{r.description}</p>
            <dl className="kv" style={{ marginTop: "0.75rem" }}>
              <dt>Organization</dt>
              <dd>{r.organization.name}</dd>
              <dt>Requested by</dt>
              <dd>
                {r.requester.full_name}
                {r.requester.email ? ` (${r.requester.email})` : ""}
              </dd>
              <dt>Category</dt>
              <dd>
                {r.category.name}
                {!r.category.is_enabled ? " (disabled)" : ""}
              </dd>
              <dt>Property</dt>
              <dd>
                {r.property.name} — {r.property.address}
                {r.property.contact_instructions ? <div className="muted small">{r.property.contact_instructions}</div> : null}
              </dd>
              <dt>Equipment</dt>
              <dd>
                {r.asset ? (
                  <>
                    {staff ? <Link href={`/assets/${r.asset.id}`}>{r.asset.code}</Link> : r.asset.code} — {r.asset.name} ({r.asset.asset_type}
                    {r.asset.serial_number ? `, S/N ${r.asset.serial_number}` : ""})
                  </>
                ) : (
                  "—"
                )}
              </dd>
              <dt>Appointment</dt>
              <dd>
                {appointment
                  ? `${fmtDateTime(appointment.start_at, tz)} → ${fmtDateTime(appointment.end_at, tz)} · ${appointment.technician_name ?? ""}`
                  : "Not scheduled"}
              </dd>
              {r.preferred_start_at ? (
                <>
                  <dt>Preferred visit</dt>
                  <dd>
                    {fmtDateTime(r.preferred_start_at, tz)}
                    {r.preferred_end_at ? ` → ${fmtDateTime(r.preferred_end_at, tz)}` : ""}
                  </dd>
                </>
              ) : null}
              <dt>SLA</dt>
              <dd>
                {r.sla.stopped_at
                  ? `Final outcome: ${r.sla.state.replace("_", " ").toLowerCase()}`
                  : r.sla.paused
                    ? "Paused while the estimate awaits approval"
                    : `Due ${fmtDateTime(r.sla.due_at, tz)}`}
                <div className="muted small">
                  Budget {fmtDuration(r.sla.budget_seconds)} of business time · {fmtDuration(r.sla.consumed_seconds)} used
                </div>
              </dd>
              {r.estimate ? (
                <>
                  <dt>Estimate</dt>
                  <dd>
                    v{r.estimate.version} · {r.estimate.status.replace("_", " ").toLowerCase()}
                  </dd>
                </>
              ) : null}
              {r.completion_note ? (
                <>
                  <dt>Completion note</dt>
                  <dd>{r.completion_note}</dd>
                </>
              ) : null}
              {r.duplicate_of ? (
                <>
                  <dt>Duplicate of</dt>
                  <dd>
                    <Link href={`/requests/${r.duplicate_of.id}`}>{r.duplicate_of.reference}</Link> · {r.duplicate_of.title}
                  </dd>
                </>
              ) : null}
              {staff && r.triage_notes ? (
                <>
                  <dt>Dispatch notes</dt>
                  <dd>{r.triage_notes}</dd>
                </>
              ) : null}
            </dl>
          </Card>
          <RequestActions request={r} />
          {staff && r.allowed_actions.includes("reclassify") ? <ReclassifyCard key={`${r.category.id}-${r.priority}-${r.duplicate_of?.id ?? ""}`} request={r} /> : null}
          <DispatchPanel request={r} />
          <EstimatePanel request={r} />
          <NotesCard request={r} />
          <FeedbackCard request={r} />
        </div>
        <div className="stack">
          <EvidenceCard request={r} />
          <MaterialsCard request={r} />
          <Timeline requestId={r.id} />
        </div>
      </div>
    </>
  );
}
