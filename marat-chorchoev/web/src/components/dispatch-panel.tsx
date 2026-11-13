"use client";

import { useState } from "react";
import { Button, Card, ErrorNote, Notice, Spinner, TextField } from "@/components/ui";
import { api, ApiError, newCommandId } from "@/lib/api";
import { addDays, fmtDateTime, fmtTime, localDate, minutesToText, zonedToUtc } from "@/lib/format";
import { useAction, useApiQuery } from "@/lib/hooks";
import { useMembership } from "@/lib/session";
import type { Candidate, RequestDetail, SlotOption } from "@/lib/types";

/**
 * Assignment and rescheduling.
 *
 * Original workflow improvement (WEB-09): the **Smart slot finder** proposes the
 * earliest bookable technician/slot pairs for this request's category, honouring the
 * requester's preferred visit, so a dispatcher can book in one click instead of
 * trial-and-error with the schedule board. See docs/PRODUCT_DECISIONS.md.
 */
export function DispatchPanel({ request }: { request: RequestDetail }) {
  const membership = useMembership();
  const tz = membership?.timezone ?? "UTC";
  const canAssign = request.allowed_actions.includes("assign");
  const canReschedule = request.allowed_actions.includes("reschedule");
  const [date, setDate] = useState(() => addDays(localDate(new Date(), tz), 1));
  const [start, setStart] = useState("10:00");
  const [minutes, setMinutes] = useState(String(request.category.default_duration_minutes));
  const [reason, setReason] = useState("");
  const [onlyEligible, setOnlyEligible] = useState(false);
  const [conflict, setConflict] = useState<string | null>(null);
  const [key] = useState(() => newCommandId("assign"));

  const startAt = zonedToUtc(date, start, tz);
  const duration = Math.max(0, Number(minutes) || 0);
  const endAt = new Date(startAt.getTime() + duration * 60_000);
  const slotValid = !Number.isNaN(startAt.getTime()) && duration >= 30;

  const suggestions = useApiQuery<{ duration_minutes: number; options: SlotOption[] }>(
    canAssign ? `/requests/${request.id}/suggestions` : null,
  );
  const candidates = useApiQuery<{ slot_error: { message: string } | null; candidates: Candidate[] }>(
    slotValid ? `/requests/${request.id}/candidates` : null,
    { start_at: startAt.toISOString(), end_at: endAt.toISOString(), eligible_only: onlyEligible },
  );

  const book = useAction(
    (target: { technician_id: string; start_at: string; end_at: string }) => {
      setConflict(null);
      const path = canReschedule ? "reschedule" : "assign";
      return api.post(
        `/requests/${request.id}/${path}`,
        { ...target, ...(canReschedule ? { reason: reason || null } : {}) },
        // Backend allows 8-100 chars: keep it short (prefix+uuid ≈ 43, + 8 + 13 ≈ 66).
        {
          "Idempotency-Key": `${key}-${target.technician_id.slice(0, 8)}-${new Date(target.start_at).getTime()}`,
        },
      );
    },
    {
      success: canReschedule ? "Rescheduled." : "Technician assigned.",
      silentError: true,
    },
  );

  if (!canAssign && !canReschedule) return null;

  const error = book.error;
  const conflictText =
    error instanceof ApiError && error.status === 409
      ? `${error.message} Pick another slot or technician.`
      : null;

  return (
    <Card title={canReschedule ? "Reschedule or reassign" : "Assign a technician"}>
      <div className="stack">
        {conflictText ? (
          <Notice kind="warn">
            <strong>Conflict (409).</strong> {conflictText}
          </Notice>
        ) : error ? (
          <ErrorNote error={error} />
        ) : null}
        {conflict ? <Notice kind="warn">{conflict}</Notice> : null}

        {canAssign ? (
          <section aria-labelledby="smart-title">
            <h3 id="smart-title">Smart slot finder</h3>
            <p className="muted small">
              Earliest eligible technician and slot for “{request.category.name}” ({minutesToText(request.category.default_duration_minutes)}),
              checked against skills, availability, time off, and existing jobs.
            </p>
            {suggestions.isLoading ? <Spinner label="Looking for slots…" /> : null}
            <ErrorNote error={suggestions.error} onRetry={() => void suggestions.refetch()} />
            {suggestions.data && suggestions.data.options.length === 0 ? (
              <Notice kind="warn">No eligible technician is free in the next 10 days. Check skills and availability under Administration.</Notice>
            ) : null}
            <div className="stack">
              {suggestions.data?.options.map((o, index) => (
                <div className="suggest row between" key={`${o.technician_id}-${o.start_at}`}>
                  <div>
                    <strong>{o.technician_name}</strong>
                    {index === 0 ? <span className="badge"> Best match</span> : null}
                    {o.matches_preference ? <span className="badge"> Matches requested time</span> : null}
                    <div className="muted small">
                      {fmtDateTime(o.start_at, tz)} – {fmtTime(o.end_at, tz)} · {minutesToText(o.week_minutes)} booked this week
                    </div>
                  </div>
                  <Button
                    small
                    loading={book.isPending}
                    onClick={() => book.mutate({ technician_id: o.technician_id, start_at: o.start_at, end_at: o.end_at })}
                  >
                    Book this
                  </Button>
                </div>
              ))}
            </div>
          </section>
        ) : null}

        <section aria-labelledby="manual-title">
          <h3 id="manual-title">Choose manually</h3>
          <div className="grid cols-3">
            <TextField label="Date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
            <TextField label="Start time" type="time" value={start} onChange={(e) => setStart(e.target.value)} />
            <TextField label="Minutes" type="number" min={30} step={15} value={minutes} onChange={(e) => setMinutes(e.target.value)} error={duration < 30 ? "At least 30 minutes." : undefined} />
          </div>
          <label className="check" style={{ margin: "0.5rem 0" }}>
            <input type="checkbox" checked={onlyEligible} onChange={(e) => setOnlyEligible(e.target.checked)} />
            Show only eligible technicians
          </label>
          {canReschedule ? (
            <TextField label="Reason (optional)" value={reason} onChange={(e) => setReason(e.target.value)} />
          ) : null}
          {candidates.isLoading ? <Spinner /> : null}
          {candidates.data?.slot_error ? <Notice kind="warn">{candidates.data.slot_error.message}</Notice> : null}
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Technician</th>
                  <th>Skills</th>
                  <th>Workload</th>
                  <th>Availability</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {candidates.data?.candidates.map((c) => (
                  <tr key={c.technician_id}>
                    <td>
                      <strong>{c.full_name}</strong>
                    </td>
                    <td>{c.skills.join(", ") || "—"}</td>
                    <td>
                      {minutesToText(c.workload.day_minutes)} today · {minutesToText(c.workload.week_minutes)} / week ({c.workload.week_jobs} jobs)
                    </td>
                    <td>
                      {c.eligible ? (
                        <span className="badge sla-ON_TRACK">✓ Available</span>
                      ) : (
                        <ul style={{ margin: 0, paddingLeft: "1rem" }}>
                          {c.reasons.map((r) => (
                            <li key={r.message} className="small">
                              {r.message}
                            </li>
                          ))}
                        </ul>
                      )}
                    </td>
                    <td>
                      <Button
                        small
                        variant="secondary"
                        disabled={!c.eligible || !slotValid}
                        loading={book.isPending}
                        onClick={() => book.mutate({ technician_id: c.technician_id, start_at: startAt.toISOString(), end_at: endAt.toISOString() })}
                      >
                        {canReschedule ? "Move here" : "Assign"}
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {candidates.data && candidates.data.candidates.length === 0 ? (
            <p className="muted">No technicians match.</p>
          ) : null}
        </section>
      </div>
    </Card>
  );
}
