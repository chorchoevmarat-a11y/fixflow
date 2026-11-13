"use client";

import { useState } from "react";
import { Button, Card, ConfirmButton, Empty, Notice, TextArea, TextField } from "@/components/ui";
import { api } from "@/lib/api";
import { fmtDateTime, fmtMoney, minutesToText, parseMoney } from "@/lib/format";
import { useAction, useApiQuery } from "@/lib/hooks";
import { useMembership } from "@/lib/session";
import type { Estimate, RequestDetail } from "@/lib/types";

interface LineDraft {
  description: string;
  quantity: string;
  price: string;
}

function laborTotal(minutes: number, rateMinor: number): number {
  return Math.floor((minutes * rateMinor + 30) / 60); // identical rounding to the server
}

function EstimateEditor({ request, base, onDone }: { request: RequestDetail; base?: Estimate; onDone: () => void }) {
  const [minutes, setMinutes] = useState(String(base?.labor_minutes ?? 60));
  const [rate, setRate] = useState(base ? (base.labor_rate_minor / 100).toFixed(2) : "1200.00");
  const [notes, setNotes] = useState(base?.notes ?? "");
  const [lines, setLines] = useState<LineDraft[]>(
    base?.lines.map((l) => ({ description: l.description, quantity: String(l.quantity), price: (l.unit_price_minor / 100).toFixed(2) })) ?? [],
  );
  const [error, setError] = useState<string | null>(null);

  const rateMinor = parseMoney(rate);
  const parsed = lines.map((l) => ({ ...l, q: Number(l.quantity), p: parseMoney(l.price) }));
  const linesOk = parsed.every((l) => l.description.trim() && Number.isInteger(l.q) && l.q > 0 && l.p !== null);
  const labor = rateMinor === null ? 0 : laborTotal(Number(minutes) || 0, rateMinor);
  const materials = parsed.reduce((sum, l) => sum + (linesOk ? l.q * (l.p ?? 0) : 0), 0);

  const body = () => ({
    labor_minutes: Number(minutes),
    labor_rate_minor: rateMinor,
    notes: notes.trim() || null,
    lines: parsed.map((l) => ({ description: l.description.trim(), quantity: l.q, unit_price_minor: l.p })),
  });
  const save = useAction(
    async (submit: boolean) => {
      const draft = base?.status === "DRAFT" ? await api.put<Estimate>(`/estimates/${base.id}`, body()) : await api.post<Estimate>(`/requests/${request.id}/estimates`, body());
      if (submit) await api.post(`/estimates/${draft.id}/submit`);
      return draft;
    },
    { success: "Estimate saved.", onSuccess: onDone },
  );

  const validate = (): boolean => {
    if (!Number.isInteger(Number(minutes)) || Number(minutes) < 0) return setError("Labor minutes must be a whole number, zero or more."), false;
    if (rateMinor === null) return setError("Enter the hourly labor rate as an amount, e.g. 1200.00."), false;
    if (!linesOk) return setError("Each material line needs a description, a positive whole quantity, and a unit price."), false;
    setError(null);
    return true;
  };

  return (
    <div className="stack">
      {base && base.status !== "DRAFT" ? <Notice>Creating version {base.version + 1}; it replaces version {base.version} once submitted.</Notice> : null}
      <div className="grid cols-2">
        <TextField label="Labor minutes" type="number" min={0} value={minutes} onChange={(e) => setMinutes(e.target.value)} />
        <TextField label="Hourly labor rate (KGS)" value={rate} onChange={(e) => setRate(e.target.value)} />
      </div>
      <h3>Material lines</h3>
      {lines.map((line, i) => (
        <div className="grid cols-4" key={i}>
          <TextField label="Description" value={line.description} onChange={(e) => setLines(lines.map((l, j) => (j === i ? { ...l, description: e.target.value } : l)))} />
          <TextField label="Quantity" type="number" min={1} value={line.quantity} onChange={(e) => setLines(lines.map((l, j) => (j === i ? { ...l, quantity: e.target.value } : l)))} />
          <TextField label="Unit price" value={line.price} onChange={(e) => setLines(lines.map((l, j) => (j === i ? { ...l, price: e.target.value } : l)))} />
          <div style={{ alignSelf: "end" }}>
            <Button variant="secondary" small onClick={() => setLines(lines.filter((_, j) => j !== i))}>
              Remove
            </Button>
          </div>
        </div>
      ))}
      <div>
        <Button variant="secondary" small onClick={() => setLines([...lines, { description: "", quantity: "1", price: "0.00" }])}>
          Add material line
        </Button>
      </div>
      <TextArea label="Notes for the requester (optional)" value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} />
      <p>
        Labor {fmtMoney(labor)} + materials {fmtMoney(materials)} = <strong>{fmtMoney(labor + materials)}</strong>
      </p>
      {error ? (
        <p className="error-text" role="alert">
          {error}
        </p>
      ) : null}
      <div className="row">
        <Button variant="secondary" loading={save.isPending} onClick={() => validate() && save.mutate(false)}>
          Save draft
        </Button>
        <Button loading={save.isPending} onClick={() => validate() && save.mutate(true)}>
          Submit for approval
        </Button>
        <Button variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

function EstimateView({ estimate, timeZone }: { estimate: Estimate; timeZone: string }) {
  return (
    <div className="stack">
      <div className="row between">
        <strong>
          Version {estimate.version} · {estimate.status.replace("_", " ").toLowerCase()}
        </strong>
        <strong>{fmtMoney(estimate.total_minor, estimate.currency)}</strong>
      </div>
      <table>
        <tbody>
          <tr>
            <td>
              Labor: {minutesToText(estimate.labor_minutes)} at {fmtMoney(estimate.labor_rate_minor, estimate.currency)}/h
            </td>
            <td>{fmtMoney(estimate.labor_total_minor, estimate.currency)}</td>
          </tr>
          {estimate.lines.map((l) => (
            <tr key={l.id}>
              <td>
                {l.description} × {l.quantity} @ {fmtMoney(l.unit_price_minor, estimate.currency)}
              </td>
              <td>{fmtMoney(l.line_total_minor, estimate.currency)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {estimate.notes ? <p className="muted">{estimate.notes}</p> : null}
      <p className="muted small">
        Prepared by {estimate.created_by}
        {estimate.submitted_at ? ` · submitted ${fmtDateTime(estimate.submitted_at, timeZone)}` : ""}
        {estimate.decided_by ? ` · ${estimate.status === "APPROVED" ? "approved" : "rejected"} by ${estimate.decided_by} ${fmtDateTime(estimate.decided_at, timeZone)}` : ""}
        {estimate.decision_reason ? ` — “${estimate.decision_reason}”` : ""}
      </p>
    </div>
  );
}

export function EstimatePanel({ request }: { request: RequestDetail }) {
  const membership = useMembership();
  const tz = membership?.timezone ?? "UTC";
  const staff = request.allowed_actions.includes("manage_estimate");
  const canDecide = request.allowed_actions.includes("decide_estimate");
  const estimates = useApiQuery<Estimate[]>(`/requests/${request.id}/estimates`);
  const [editing, setEditing] = useState<"new" | "draft" | null>(null);
  const [reason, setReason] = useState("");
  const [reasonError, setReasonError] = useState<string | null>(null);

  const decide = useAction(
    (input: { estimate: Estimate; approve: boolean; reason?: string }) =>
      input.approve
        ? api.post(`/estimates/${input.estimate.id}/approve`, { version: input.estimate.version })
        : api.post(`/estimates/${input.estimate.id}/reject`, { version: input.estimate.version, reason: input.reason }),
    { success: "Decision recorded." },
  );
  const withdraw = useAction((input: { id: string; reason: string }) => api.post(`/estimates/${input.id}/withdraw`, { reason: input.reason }), {
    success: "Estimate withdrawn.",
  });
  const discard = useAction((id: string) => api.del(`/estimates/${id}`), { success: "Draft discarded." });

  const list = estimates.data ?? [];
  const current = list.find((e) => e.status !== "SUPERSEDED" && e.status !== "DRAFT");
  const draft = list.find((e) => e.status === "DRAFT");
  const history = list.filter((e) => e !== current && e !== draft);
  if (!staff && !canDecide && list.length === 0) return null;

  return (
    <Card
      title="Estimate"
      actions={
        staff && !editing ? (
          <Button small variant="secondary" onClick={() => setEditing(draft ? "draft" : "new")}>
            {draft ? "Edit draft" : current ? "New version" : "Create estimate"}
          </Button>
        ) : null
      }
    >
      {editing ? (
        <EstimateEditor request={request} base={editing === "draft" ? draft : current} onDone={() => setEditing(null)} />
      ) : (
        <div className="stack">
          {list.length === 0 ? <Empty title="No estimate yet" /> : null}
          {current ? <EstimateView estimate={current} timeZone={tz} /> : null}
          {canDecide && current?.status === "AWAITING_APPROVAL" ? (
            <div className="stack">
              <Notice kind="warn">Review version {current.version} and decide. Work cannot start until it is approved.</Notice>
              <div className="row">
                <ConfirmButton
                  label="Approve estimate"
                  variant="primary"
                  title={`Approve version ${current.version}?`}
                  message={`You approve ${fmtMoney(current.total_minor, current.currency)} (an estimate, not an invoice).`}
                  onConfirm={() => decide.mutate({ estimate: current, approve: true })}
                  loading={decide.isPending}
                />
              </div>
              <TextArea label="Reason for rejecting" value={reason} onChange={(e) => setReason(e.target.value)} error={reasonError} rows={2} />
              <div>
                <Button
                  variant="danger"
                  loading={decide.isPending}
                  onClick={() => {
                    if (reason.trim().length < 3) return setReasonError("Give a reason of at least 3 characters.");
                    setReasonError(null);
                    decide.mutate({ estimate: current, approve: false, reason: reason.trim() });
                  }}
                >
                  Reject estimate
                </Button>
              </div>
            </div>
          ) : null}
          {staff && current && ["AWAITING_APPROVAL", "APPROVED", "REJECTED"].includes(current.status) ? (
            <ConfirmButton
              label="Withdraw estimate"
              small
              variant="secondary"
              title="Withdraw this estimate?"
              message="Work can then proceed without an estimate, or you can create a new version."
              needsReason
              onConfirm={(r) => withdraw.mutate({ id: current.id, reason: r })}
              loading={withdraw.isPending}
            />
          ) : null}
          {staff && draft ? (
            <div className="row between">
              <span className="muted">Draft version {draft.version}: {fmtMoney(draft.total_minor, draft.currency)}</span>
              <Button variant="ghost" small loading={discard.isPending} onClick={() => discard.mutate(draft.id)}>
                Discard draft
              </Button>
            </div>
          ) : null}
          {history.length ? (
            <details>
              <summary>Earlier versions ({history.length})</summary>
              <div className="stack" style={{ marginTop: "0.5rem" }}>
                {history.filter((e) => e.status !== "DRAFT").map((e) => (
                  <div key={e.id} className="note">
                    <EstimateView estimate={e} timeZone={tz} />
                  </div>
                ))}
              </div>
            </details>
          ) : null}
        </div>
      )}
    </Card>
  );
}
