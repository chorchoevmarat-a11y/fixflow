"use client";

import { useEffect, useState } from "react";
import { Button, Card, Empty, SelectField, TextArea } from "@/components/ui";
import { api, fetchBlobUrl, newCommandId } from "@/lib/api";
import { fmtDateTime, fmtMoney } from "@/lib/format";
import { useAction, useApiQuery } from "@/lib/hooks";
import { useMembership } from "@/lib/session";
import type { ActivityItem, FileItem, MaterialUsage, NoteItem, Page, RequestDetail } from "@/lib/types";

function AuthImage({ file }: { file: FileItem }) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let revoked: string | null = null;
    let active = true;
    fetchBlobUrl(file.content_url)
      .then((u) => {
        if (active) {
          revoked = u;
          setUrl(u);
        } else URL.revokeObjectURL(u);
      })
      .catch(() => active && setFailed(true));
    return () => {
      active = false;
      if (revoked) URL.revokeObjectURL(revoked);
    };
  }, [file.content_url]);
  if (failed) return <div className="note small">Image unavailable</div>;
  if (!url) return <div className="note small">Loading…</div>;
  return (
    <a href={url} target="_blank" rel="noreferrer">
      {/* eslint-disable-next-line @next/next/no-img-element -- authorized blob URL, not optimizable */}
      <img src={url} alt={`${file.kind.toLowerCase()} photo: ${file.original_name}`} />
    </a>
  );
}

export function EvidenceCard({ request }: { request: RequestDetail }) {
  const files = useApiQuery<FileItem[]>(`/requests/${request.id}/files`);
  const canAdd = request.allowed_actions.includes("add_evidence");
  const upload = useAction(
    async (file: File) => {
      const form = new FormData();
      form.set("file", file);
      form.set("kind", "COMPLETION");
      form.set("client_command_id", newCommandId("evi"));
      return api.upload(`/requests/${request.id}/files`, form);
    },
    { success: "Photo uploaded." },
  );
  const groups: [string, string][] = [
    ["INTAKE", "Reported by requester"],
    ["NOTE", "Attached to notes"],
    ["COMPLETION", "Completion evidence"],
  ];
  return (
    <Card title="Photos & evidence">
      {files.data && files.data.length === 0 ? <Empty title="No photos yet" /> : null}
      {groups.map(([kind, label]) => {
        const items = files.data?.filter((f) => f.kind === kind) ?? [];
        if (!items.length) return null;
        return (
          <div key={kind} style={{ marginBottom: "0.75rem" }}>
            <h3>{label}</h3>
            <div className="thumbs">
              {items.map((f) => (
                <AuthImage key={f.id} file={f} />
              ))}
            </div>
          </div>
        );
      })}
      {canAdd ? (
        <div className="field">
          <label htmlFor="more-evidence">Add completion photo</label>
          <input
            id="more-evidence"
            type="file"
            accept="image/jpeg,image/png,image/webp"
            disabled={upload.isPending}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) upload.mutate(f);
              e.target.value = "";
            }}
          />
        </div>
      ) : null}
    </Card>
  );
}

export function NotesCard({ request }: { request: RequestDetail }) {
  const membership = useMembership();
  const tz = membership?.timezone ?? "UTC";
  const notes = useApiQuery<NoteItem[]>(`/requests/${request.id}/notes`);
  const [body, setBody] = useState("");
  const [visibility, setVisibility] = useState("PUBLIC");
  const [error, setError] = useState<string | null>(null);
  const [command, setCommand] = useState(() => newCommandId("note"));
  const canAdd = request.allowed_actions.includes("add_note");
  const canInternal = membership?.role !== "REQUESTER";

  const add = useAction(
    () => api.post(`/requests/${request.id}/notes`, { body: body.trim(), visibility, client_command_id: command }),
    {
      success: "Note added.",
      onSuccess: () => {
        setBody("");
        setCommand(newCommandId("note"));
      },
    },
  );
  return (
    <Card title="Messages & notes">
      <div className="stack">
        {notes.data && notes.data.length === 0 ? <Empty title="No notes yet" /> : null}
        {notes.data?.map((n) => (
          <div key={n.id} className={`note${n.visibility === "INTERNAL" ? " internal" : ""}`}>
            <div className="row between small muted">
              <span>
                <strong>{n.author_name}</strong> · {n.author_role.toLowerCase()}
                {n.visibility === "INTERNAL" ? " · internal only" : ""}
              </span>
              <span>{fmtDateTime(n.created_at, tz)}</span>
            </div>
            <p style={{ whiteSpace: "pre-wrap" }}>{n.body}</p>
          </div>
        ))}
        {canAdd ? (
          <form
            className="stack"
            onSubmit={(e) => {
              e.preventDefault();
              if (add.isPending) return;
              if (!body.trim()) return setError("Write a note first.");
              setError(null);
              add.mutate(undefined);
            }}
          >
            <TextArea label="Add a note" value={body} onChange={(e) => setBody(e.target.value)} error={error} rows={3} />
            <div className="row between">
              {canInternal ? (
                <SelectField label="Visible to" value={visibility} onChange={(e) => setVisibility(e.target.value)}>
                  <option value="PUBLIC">Everyone on this request</option>
                  <option value="INTERNAL">Staff and technicians only</option>
                </SelectField>
              ) : (
                <span />
              )}
              <Button type="submit" loading={add.isPending} style={{ alignSelf: "end" }}>
                Add note
              </Button>
            </div>
          </form>
        ) : null}
      </div>
    </Card>
  );
}

export function MaterialsCard({ request }: { request: RequestDetail }) {
  const usage = useApiQuery<MaterialUsage[]>(`/requests/${request.id}/materials`);
  const currency = request.estimate?.currency ?? "KGS";
  if (!usage.data?.length) return null;
  const total = usage.data.reduce((sum, u) => sum + (u.total_minor ?? 0), 0);
  const showMoney = usage.data[0]?.total_minor !== undefined;
  return (
    <Card title="Materials used">
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Item</th>
              <th>Qty</th>
              {showMoney ? <th>Cost (price at the time)</th> : null}
              <th>By</th>
            </tr>
          </thead>
          <tbody>
            {usage.data.map((u) => (
              <tr key={u.id}>
                <td>
                  {u.item_code} — {u.item_name}
                </td>
                <td>
                  {u.quantity} {u.unit}
                </td>
                {showMoney ? <td>{fmtMoney(u.total_minor ?? 0, currency)}</td> : null}
                <td>{u.technician_name}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {showMoney ? <p className="muted small">Total: {fmtMoney(total, currency)}</p> : null}
    </Card>
  );
}

export function Timeline({ requestId }: { requestId: string }) {
  const membership = useMembership();
  const tz = membership?.timezone ?? "UTC";
  const activity = useApiQuery<Page<ActivityItem>>(`/requests/${requestId}/activity`, { page_size: 100 });
  return (
    <Card title="Activity">
      {activity.data && activity.data.items.length === 0 ? <Empty title="No activity" /> : null}
      <ol className="timeline">
        {activity.data?.items.map((a) => (
          <li key={a.id}>
            <div>{a.summary}</div>
            <div className="muted small">
              {a.actor_name} · {fmtDateTime(a.created_at, tz)}
            </div>
          </li>
        ))}
      </ol>
    </Card>
  );
}

export function FeedbackCard({ request }: { request: RequestDetail }) {
  const [rating, setRating] = useState("5");
  const [comment, setComment] = useState("");
  const give = useAction(() => api.post(`/requests/${request.id}/feedback`, { rating: Number(rating), comment: comment.trim() || null }), {
    success: "Thanks for your feedback.",
  });
  if (request.feedback) {
    return (
      <Card title="Your feedback">
        <p>
          {"★".repeat(request.feedback.rating)}
          {"☆".repeat(5 - request.feedback.rating)} ({request.feedback.rating}/5)
        </p>
        {request.feedback.comment ? <p className="muted">{request.feedback.comment}</p> : null}
      </Card>
    );
  }
  if (!request.allowed_actions.includes("give_feedback")) return null;
  return (
    <Card title="How did we do?">
      <div className="stack">
        <SelectField label="Rating" value={rating} onChange={(e) => setRating(e.target.value)}>
          {[5, 4, 3, 2, 1].map((n) => (
            <option key={n} value={n}>
              {n} — {["", "Poor", "Fair", "Good", "Very good", "Excellent"][n]}
            </option>
          ))}
        </SelectField>
        <TextArea label="Comment (optional)" value={comment} onChange={(e) => setComment(e.target.value)} rows={2} />
        <div>
          <Button loading={give.isPending} onClick={() => give.mutate(undefined)}>
            Send feedback
          </Button>
        </div>
      </div>
    </Card>
  );
}
